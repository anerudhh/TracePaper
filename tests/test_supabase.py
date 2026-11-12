"""Real PostgreSQL RPC semantics plus an HTTP object-storage contract double.

Run with TRACEPAPER_TEST_POSTGRES_CONTAINER pointing to a container initialized
with tests/supabase_roles.sql and supabase/migrations/001_tracepaper.sql.
No connection to a hosted Supabase project is implied by these checks.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import fitz
import httpx
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.store import SupabaseStore

CONTAINER = os.getenv("TRACEPAPER_TEST_POSTGRES_CONTAINER")


def sql(statement, check=True):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        )
    }
    r = subprocess.run(
        [
            "docker",
            "--host=unix:///var/run/docker.sock",
            "exec",
            "-i",
            CONTAINER,
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
        ],
        input=statement,
        text=True,
        capture_output=True,
        env=env,
    )
    if check and r.returncode:
        raise AssertionError(r.stderr)
    return r


def literal(value, key):
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list) and key in ("p_tokens", "p_paper_ids"):
        return (
            "array["
            + ",".join("'" + v.replace("'", "''") + "'" for v in value)
            + "]::text[]"
        )
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    return "'" + value.replace("'", "''") + "'"


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    if not CONTAINER:
        pytest.skip(
            "Set TRACEPAPER_TEST_POSTGRES_CONTAINER for real PostgreSQL integration"
        )
    sql(
        "truncate public.tp_papers,public.tp_chunks,public.tp_history,public.tp_deleted_files restart identity cascade;"
    )
    monkeypatch.setattr(main, "DATA", tmp_path)
    monkeypatch.setenv("TRACEPAPER_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.delenv("TRACEPAPER_PASSWORD", raising=False)
    objects = {}
    faults = {"upload": False, "delete": False}
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["apikey"] == "test-service-role-key"
        if request.url.path.startswith("/rest/v1/rpc/tp_"):
            name = request.url.path.rsplit("/", 1)[-1]
            assert re.fullmatch(r"tp_[a-z_]+", name)
            params = json.loads(request.read())
            args = ",".join(k + "=>" + literal(v, k) for k, v in params.items())
            r = sql("set role service_role;select public." + name + "(" + args + ");")
            return httpx.Response(
                200,
                content=r.stdout.strip() or "null",
                headers={"Content-Type": "application/json"},
            )
        key = request.url.path
        if request.method == "POST":
            if faults["upload"]:
                return httpx.Response(503, json={"error": "test upload outage"})
            objects[key] = request.read()
            return httpx.Response(200, json={"Key": key})
        if request.method == "DELETE":
            if faults["delete"]:
                return httpx.Response(503, json={"error": "test deletion outage"})
            objects.pop(key, None)
            return httpx.Response(200, json={})
        if key not in objects:
            return httpx.Response(404, json={"error": "not found"})
        body = objects[key]
        if request.headers.get("range") == "bytes=0-3":
            return httpx.Response(
                206,
                content=body[:4],
                headers={
                    "Content-Range": f"bytes 0-3/{len(body)}",
                    "Content-Length": "4",
                    "Accept-Ranges": "bytes",
                },
            )
        return httpx.Response(
            200, content=body, headers={"Content-Length": str(len(body))}
        )

    real = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    with patch("backend.store.httpx.Client", side_effect=client_factory):
        with TestClient(main.app) as client:
            yield client, objects, faults, requests


def upload_ready(client):
    doc = fitz.open()
    doc.new_page().insert_text(
        (50, 60), "Photosynthesis converts light into chemical energy in plants."
    )
    doc.new_page().insert_text(
        (50, 60), "Chlorophyll captures blue and red wavelengths of light."
    )
    r = client.post("/api/papers", files={"file": ("Plants.pdf", doc.tobytes())})
    assert r.status_code == 202, r.text
    pid = r.json()["id"]
    for _ in range(100):
        row = client.get("/api/papers").json()["items"][0]
        if row["status"] not in ("queued", "indexing", "uploading"):
            break
        time.sleep(0.05)
    assert row["status"] == "ready", row
    return pid


def test_hosted_library_survives_loss_of_container_cache(hosted):
    client, objects, _, requests = hosted
    pid = upload_ready(client)
    answer = client.post("/api/ask", json={"question": "chlorophyll"}).json()
    assert answer["sources"][0]["page"] == 2 and answer["sources"][0]["paper_id"] == pid
    for path in main.DATA.iterdir():
        path.unlink()
    assert not list(main.DATA.iterdir())
    main.initialize()
    assert client.get("/api/papers").json()["total"] == 1
    assert client.get("/api/history/" + answer["id"]).json() == answer
    file = client.get("/api/papers/" + pid + "/file", headers={"Range": "bytes=0-3"})
    assert file.status_code == 206 and file.content == b"%PDF"
    assert objects and "Content-Range" in file.headers
    assert not (main.DATA / "library.db").exists()
    # Simulate termination during indexing, not just an ordinary service restart.
    main.get_store().status(pid, "indexing")
    main.initialize()
    for _ in range(100):
        row = client.get("/api/papers").json()["items"][0]
        if row["status"] == "ready":
            break
        time.sleep(0.05)
    assert row["status"] == "ready"
    assert any(
        r.method == "GET" and r.url.path.startswith("/storage/") for r in requests
    )


def test_hosted_deletion_retries_object_cleanup_and_removes_history(hosted):
    client, objects, faults, _ = hosted
    pid = upload_ready(client)
    answer = client.post("/api/ask", json={"question": "chlorophyll"}).json()
    faults["delete"] = True
    r = client.delete("/api/papers/" + pid)
    assert r.json() == {"ok": True, "pending_cleanup": True}
    assert client.get("/api/papers").json()["total"] == 0
    assert client.get("/api/history/" + answer["id"]).status_code == 404
    assert objects
    faults["delete"] = False
    main.initialize()
    assert not objects and not main.get_store().rpc("deleted_files")


def test_hosted_failed_upload_has_a_deletable_failed_record(hosted):
    client, _, faults, _ = hosted
    faults["upload"] = True
    r = client.post("/api/papers", files={"file": ("bad-transfer.pdf", b"%PDF-test")})
    assert r.status_code == 503
    row = client.get("/api/papers").json()["items"][0]
    assert row["status"] == "failed"
    assert client.delete("/api/papers/" + row["id"]).json()["ok"]
    assert client.get("/api/papers").json()["total"] == 0


def test_hosted_tables_and_rpc_are_not_executable_by_anonymous_users(hosted):
    for statement in (
        "select * from public.tp_papers;",
        "select public.tp_list_papers();",
        "select public.tp_get_paper('anything');",
    ):
        result = sql("set role anon;" + statement, check=False)
        assert result.returncode != 0 and "permission denied" in result.stderr
    result = sql("select public from storage.buckets where id='tracepaper';")
    assert result.stdout.strip() == "f"


def test_supabase_configuration_does_not_silently_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACEPAPER_STORAGE", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="requires SUPABASE_URL"):
        SupabaseStore(tmp_path)


def test_migration_explicitly_requests_writes_when_session_defaults_read_only(hosted):
    # Reproduce the provider's failure without changing the database-wide defaults.
    before = sql(
        "set default_transaction_read_only=on; begin; create table public.readonly_regression_probe(id integer);",
        check=False,
    )
    assert before.returncode != 0 and "read-only transaction" in before.stderr
    migration = (
        Path(__file__).resolve().parents[1] / "supabase/migrations/001_tracepaper.sql"
    ).read_text()
    after = sql("set default_transaction_read_only=on;\n" + migration, check=False)
    assert after.returncode == 0, after.stderr
    assert json.loads(sql("select public.tp_health();").stdout)["ready"]
