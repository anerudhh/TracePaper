import json
from pathlib import Path
from unittest.mock import MagicMock
import httpx
import pytest
from scripts import deploy_space


def test_deployment_configures_only_free_cpu_and_keeps_credentials_out_of_source(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "supabase/migrations").mkdir(parents=True)
    (root / "supabase/migrations/001_tracepaper.sql").write_text("select 1;")
    (root / "deploy").mkdir()
    (root / "deploy/SPACE_README.md").write_text(
        "---\nsdk: docker\napp_port: 8000\n---\n"
    )
    (root / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setattr(deploy_space, "ROOT", root)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/api-keys") and request.method == "GET":
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/api-keys") and request.method == "POST":
            return httpx.Response(
                201, json={"api_key": "fake-dedicated-storage-secret"}
            )
        return httpx.Response(200, json={})

    api = MagicMock()
    api.repo_info.return_value.sdk = "docker"
    api.get_space_runtime.return_value.hardware = "cpu-basic"
    api.get_space_runtime.return_value.requested_hardware = "cpu-basic"

    def inspect_upload(**kwargs):
        folder = Path(kwargs["folder_path"])
        assert (folder / "README.md").read_text().startswith("---\nsdk: docker")
        for p in folder.rglob("*"):
            if p.is_file():
                assert "fake-dedicated-storage-secret" not in p.read_text()
                assert "fake-workspace-password" not in p.read_text()

    api.upload_folder.side_effect = inspect_upload
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        deploy_space.deploy(
            "owner/tracepaper",
            "https://" + "a" * 20 + ".supabase.co",
            api,
            client,
            ["Dockerfile", "deploy/SPACE_README.md"],
            "fake-workspace-password",
        )
    kwargs = api.create_repo.call_args.kwargs
    assert (
        kwargs["space_sdk"] == "docker"
        and "space_hardware" not in kwargs
        and "space_volumes" not in kwargs
    )
    secrets = {
        c.kwargs["key"]: c.kwargs["value"] for c in api.add_space_secret.call_args_list
    }
    assert secrets == {
        "SUPABASE_SERVICE_ROLE_KEY": "fake-dedicated-storage-secret",
        "TRACEPAPER_PASSWORD": "fake-workspace-password",
    }
    assert any(
        r.url.path.endswith("/database/query")
        and json.loads(r.content)["read_only"] is False
        for r in calls
    )


def test_deployment_rejects_dashboard_urls_and_foreign_api_origins():
    for url in [
        "https://supabase.com/dashboard/project/" + "a" * 20,
        "http://attacker.example",
        "https://attacker.example/supabase.co",
    ]:
        with pytest.raises(ValueError):
            deploy_space.project_ref(url)
    assert deploy_space.project_ref("https://" + "a" * 20 + ".supabase.co") == "a" * 20


def test_deployment_manifest_excludes_secrets_uploads_and_caches(tmp_path, monkeypatch):
    required = [
        "Dockerfile",
        "backend/main.py",
        "backend/store.py",
        "supabase/migrations/001_tracepaper.sql",
        "deploy/SPACE_README.md",
    ]
    sensitive = [
        ".env",
        ".env.production",
        "data/private.pdf",
        ".venv/token",
        "web/node_modules/cache",
    ]
    for name in required + sensitive:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    monkeypatch.setattr(deploy_space, "ROOT", tmp_path)
    monkeypatch.setattr(
        deploy_space.subprocess,
        "check_output",
        lambda *a, **kw: "\0".join(required + sensitive).encode(),
    )
    assert set(deploy_space.deployment_files()) == set(required)
