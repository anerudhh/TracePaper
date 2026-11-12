import json
from unittest.mock import patch
import httpx
import pytest
from scripts.verify_deployment import verify, wait_ready


def test_live_verifier_checks_storage_restart_and_removes_only_its_sample():
    state = {"instance": "before", "created": False, "deleted": False, "answer": None}

    def handler(request):
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(
                200, json={"status": "ok", "instance_id": state["instance"]}
            )
        if path == "/":
            return httpx.Response(200, text="<title>TracePaper</title>")
        if path == "/api/login":
            assert json.loads(request.content)["password"] == "test-workspace-password"
            return httpx.Response(
                200,
                json={"ok": True},
                headers={"Set-Cookie": "tracepaper=test-session; Path=/; HttpOnly"},
            )
        if not request.headers.get("cookie"):
            return httpx.Response(401, json={})
        if path == "/api/config":
            return httpx.Response(200, json={"storage": "supabase"})
        if path == "/api/papers" and request.method == "POST":
            assert b"deployment-check-" in request.content
            assert "x-provider-key" not in request.headers
            state["created"] = True
            return httpx.Response(
                202, json={"id": "verification-document", "duplicate": False}
            )
        if path == "/api/papers":
            return httpx.Response(
                200,
                json={"items": [{"id": "verification-document", "status": "ready"}]},
            )
        if path == "/api/ask":
            assert json.loads(request.content)["paper_ids"] == ["verification-document"]
            state["answer"] = {
                "id": "answer-1",
                "mode": "extractive",
                "sources": [{"page": 2}],
            }
            return httpx.Response(200, json=state["answer"])
        if path.endswith("/file"):
            return httpx.Response(206, content=b"%PDF")
        if path.startswith("/api/history/"):
            return httpx.Response(200, json=state["answer"])
        if request.method == "DELETE":
            assert path == "/api/papers/verification-document"
            state["deleted"] = True
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("Unexpected request")

    def restart():
        state["instance"] = "after"

    with httpx.Client(
        base_url="https://test.example", transport=httpx.MockTransport(handler)
    ) as client:
        verify(client, "test-workspace-password", restart)
    assert state["created"] and state["deleted"] and state["instance"] == "after"


def test_live_verifier_does_not_accept_a_stale_instance_as_restart_proof():
    with httpx.Client(
        base_url="https://test.example",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"status": "ok", "instance_id": "unchanged"}
            )
        ),
    ) as client:
        with patch("scripts.verify_deployment.time.sleep"):
            with pytest.raises(RuntimeError, match="deadline"):
                wait_ready(client, attempts=2, previous_instance="unchanged")
