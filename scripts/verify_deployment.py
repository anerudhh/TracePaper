"""Verify the public deployment without logging credentials or calling a model."""

import argparse
import os
from pathlib import Path
import re
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]


def wait_ready(client, attempts=60, delay=10, previous_instance=None):
    for _ in range(attempts):
        try:
            r = client.get("/api/health", timeout=10)
            if r.status_code == 200 and r.json().get("status") == "ok":
                health = r.json()
                if previous_instance is None or (
                    health.get("instance_id")
                    and health["instance_id"] != previous_instance
                ):
                    return health
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(delay)
    raise RuntimeError(
        "The Space did not become healthy before the verification deadline."
    )


def verify(client, password, restart=None):
    health = wait_ready(client)
    response = client.get("/")
    assert response.status_code == 200 and "TracePaper" in response.text, (
        "Interface was not served"
    )
    assert client.get("/api/papers").status_code == 401, "Workspace is not protected"
    response = client.post("/api/login", json={"password": password})
    assert response.status_code == 200, "Workspace login failed"
    assert client.get("/api/config").json().get("storage") == "supabase", (
        "Hosted storage mode is not enabled"
    )
    name = "deployment-check-" + uuid.uuid4().hex + ".pdf"
    # A PDF comment changes the digest, avoiding deletion of an existing sample document.
    content = (
        (ROOT / "examples/tracepaper-field-notes.pdf").read_bytes()
        + b"\n% deployment check "
        + uuid.uuid4().hex.encode()
        + b"\n"
    )
    pid = None
    created = False
    try:
        response = client.post(
            "/api/papers",
            files={"file": (name, content, "application/pdf")},
            timeout=120,
        )
        assert response.status_code == 202, "Sample upload failed"
        pid = response.json()["id"]
        created = not response.json().get("duplicate")
        for _ in range(60):
            items = client.get("/api/papers", params={"q": name}).json()["items"]
            paper = next((p for p in items if p["id"] == pid), None)
            if paper and paper["status"] == "ready":
                break
            if paper and paper["status"] == "failed":
                raise RuntimeError("Sample indexing failed")
            time.sleep(2)
        else:
            raise RuntimeError("Sample indexing did not finish")
        response = client.post(
            "/api/ask",
            json={
                "question": "How does citation coverage differ from citation correctness?",
                "paper_ids": [pid],
            },
        )
        assert response.status_code == 200, "Document query failed"
        answer = response.json()
        assert answer["mode"] == "extractive" and answer["sources"][0]["page"] == 2, (
            "Expected citation was not retrieved"
        )
        response = client.get(
            "/api/papers/" + pid + "/file", headers={"Range": "bytes=0-3"}
        )
        assert response.status_code == 206 and response.content == b"%PDF", (
            "Original PDF range request failed"
        )
        assert client.get("/api/history/" + answer["id"]).json() == answer, (
            "Saved answer was not available"
        )
        if restart:
            restart()
            # Require a newly booted process rather than accepting stale health.
            if not health.get("instance_id"):
                raise RuntimeError(
                    "The deployment does not expose a restart instance identifier"
                )
            wait_ready(client, previous_instance=health["instance_id"])
            assert client.get("/api/papers", params={"q": name}).json()["items"], (
                "Documents were lost after restart"
            )
            assert client.get("/api/history/" + answer["id"]).json() == answer, (
                "Answer history was lost after restart"
            )
        print(
            "Verified: HTTPS interface, password gate, Supabase mode, PDF upload/indexing, page-2 retrieval, PDF range and answer history"
            + (", including restart persistence." if restart else ".")
        )
    finally:
        if pid and created:
            # Only the uniquely named verification document and its answer are removed.
            response = client.delete("/api/papers/" + pid)
            if response.status_code != 200 or response.json().get("pending_cleanup"):
                raise RuntimeError(
                    "Verification document cleanup is incomplete; inspect it before retrying"
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--space", default="tracepaper")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    for value in (args.namespace, args.space):
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", value):
            parser.error("Invalid account or Space name")
    password = os.getenv("TRACEPAPER_PASSWORD")
    if not password:
        parser.error("Set TRACEPAPER_PASSWORD securely before verification")
    restart = None
    if args.restart:
        from huggingface_hub import HfApi

        api = HfApi(token=os.environ["HF_TOKEN"])
        restart = lambda: api.restart_space(repo_id=args.namespace + "/" + args.space)
    host = (args.namespace + "-" + args.space).lower().replace("_", "-")
    with httpx.Client(base_url="https://" + host + ".hf.space", timeout=60) as client:
        verify(client, password, restart)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        # Provider responses and secrets do not belong in CI logs.
        print(
            "Live verification failed ("
            + type(error).__name__
            + "). Check the Space status and hosting secret configuration. No credential values are included."
        )
        raise SystemExit(1) from None
