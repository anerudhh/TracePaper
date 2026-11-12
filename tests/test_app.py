import io
import time
from unittest.mock import patch
import fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient
from backend import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA", tmp_path)
    for name in (
        "OPENAI_API_KEY",
        "TRACEPAPER_GEMINI_KEY",
        "GEMINI_API_KEY",
        "TRACEPAPER_PROVIDER",
        "TRACEPAPER_MODEL",
        "TRACEPAPER_GEMINI_MODEL",
        "TRACEPAPER_OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("TRACEPAPER_PASSWORD", raising=False)
    with TestClient(main.app) as c:
        yield c


def pdf_bytes():
    doc = fitz.open()
    doc.new_page().insert_text(
        (60, 60), "Photosynthesis converts light energy into chemical energy in plants."
    )
    doc.new_page().insert_text(
        (60, 60), "Chlorophyll absorbs light most strongly in blue and red wavelengths."
    )
    return doc.tobytes()


def add(client, name="Plants.pdf", content=None):
    r = client.post("/api/papers", files={"file": (name, content or pdf_bytes())})
    assert r.status_code == 202, r.text
    for _ in range(100):
        papers = client.get("/api/papers").json()["items"]
        p = next(p for p in papers if p["id"] == r.json()["id"])
        if p["status"] not in ("queued", "indexing"):
            return p
        time.sleep(0.03)
    pytest.fail("Indexing timed out")


def test_pdf_retrieval_page_and_persistence(client):
    p = add(client)
    assert p["status"] == "ready" and p["pages"] == 2
    a = client.post(
        "/api/ask", json={"question": "What wavelengths does chlorophyll absorb?"}
    ).json()
    assert a["sources"][0]["page"] == 2
    assert a["sources"][0]["paper_id"] == p["id"]
    assert a["mode"] == "extractive" and a["claims"]
    assert client.get("/api/history/" + a["id"]).json() == a
    assert client.get(
        "/api/papers/" + p["id"] + "/file"
    ).content == pdf_bytes() or client.get(
        "/api/papers/" + p["id"] + "/file"
    ).content.startswith(b"%PDF")
    main.initialize()
    assert client.get("/api/papers").json()["total"] == 1


def test_docx_uses_sections(client):
    doc = Document()
    doc.add_paragraph(
        "Quantum entanglement describes correlations between distant particles in a shared quantum state."
    )
    out = io.BytesIO()
    doc.save(out)
    p = add(client, "Physics.docx", out.getvalue())
    assert p["status"] == "ready" and p["kind"] == "docx"
    a = client.post(
        "/api/ask", json={"question": "Explain quantum entanglement"}
    ).json()
    assert a["sources"][0]["kind"] == "docx" and a["sources"][0]["page"] == 1


def test_duplicates(client):
    data = pdf_bytes()
    add(client, content=data)
    r = client.post("/api/papers", files={"file": ("duplicate.pdf", data)})
    assert r.json()["duplicate"]
    assert client.get("/api/papers").json()["total"] == 1


def test_bad_uploads(client):
    assert (
        client.post("/api/papers", files={"file": ("bad.exe", b"x")}).status_code == 415
    )
    assert (
        client.post("/api/papers", files={"file": ("empty.pdf", b"")}).status_code
        == 400
    )
    p = add(client, "corrupt.pdf", b"invalid PDF bytes")
    assert p["status"] == "failed" and p["error"]


def test_no_evidence_and_scope(client):
    add(client)
    for question, scope in [
        ("zygomorphic xylophones", []),
        ("photosynthesis", ["nonexistent"]),
    ]:
        a = client.post(
            "/api/ask", json={"question": question, "paper_ids": scope}
        ).json()
        assert a["insufficient"] and not a["claims"]
    assert client.post("/api/ask", json={"question": "x"}).status_code == 422


def test_delete_removes_history_index_and_file(client):
    p = add(client)
    a = client.post("/api/ask", json={"question": "photosynthesis"}).json()
    assert client.delete("/api/papers/" + p["id"]).status_code == 200
    assert not main.paper_path(p["id"], "pdf").exists()
    assert client.get("/api/history/" + a["id"]).status_code == 404
    assert client.post("/api/ask", json={"question": "photosynthesis"}).json()[
        "insufficient"
    ]


def test_pagination_filter(client):
    add(client)
    assert client.get("/api/papers?q=Plants").json()["total"] == 1
    assert client.get("/api/papers?q=Missing").json()["total"] == 0
    assert client.get("/api/papers?offset=1").json()["items"] == []


def test_access_and_origin(client, monkeypatch):
    monkeypatch.setenv("TRACEPAPER_PASSWORD", "test-only-password")
    assert client.get("/api/papers").status_code == 401
    assert client.post("/api/login", json={"password": "bad"}).status_code == 401
    assert (
        client.post("/api/login", json={"password": "test-only-password"}).status_code
        == 200
    )
    assert client.get("/api/papers").status_code == 200
    assert (
        client.post(
            "/api/ask",
            headers={"Origin": "https://evil.example"},
            json={"question": "anything"},
        ).status_code
        == 403
    )
    client.post("/api/logout")
    assert client.get("/api/history").status_code == 401


def test_generation_rejects_invalid_citation(client, monkeypatch):
    add(client)
    client.headers["X-Provider-Key"] = "test-placeholder"
    response = __import__("httpx").Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": '{"claims":[{"text":"Invented claim","citations":[999]}]}'
                    }
                }
            ]
        },
        request=__import__("httpx").Request("POST", "https://api.openai.com"),
    )
    with patch("backend.main.httpx.Client") as provider:
        provider.return_value.__enter__.return_value.post.return_value = response
        a = client.post(
            "/api/ask", json={"question": "photosynthesis", "provider": "openai"}
        ).json()
    assert a["mode"] == "generated" and a["insufficient"] and not a["claims"]


def test_generation_and_provider_failure(client, monkeypatch):
    add(client)
    client.headers["X-Provider-Key"] = "test-placeholder"
    response = __import__("httpx").Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": '{"claims":[{"text":"Plants convert light to chemical energy.","citations":[1]}]}'
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
        request=__import__("httpx").Request("POST", "https://api.openai.com"),
    )
    with patch("backend.main.httpx.Client") as provider:
        provider.return_value.__enter__.return_value.post.return_value = response
        a = client.post(
            "/api/ask", json={"question": "photosynthesis", "provider": "openai"}
        ).json()
    assert (
        a["mode"] == "generated"
        and a["claims"][0]["citations"] == [1]
        and a["estimated_cost_usd"] > 0
    )
    with patch(
        "backend.main.httpx.Client", side_effect=RuntimeError("provider unavailable")
    ):
        a = client.post(
            "/api/ask", json={"question": "photosynthesis", "provider": "openai"}
        ).json()
    assert a["mode"] == "extractive" and a["warning"] and a["claims"]


def test_scanned_pdf_ocr(client, monkeypatch):
    import shutil

    if not shutil.which("tesseract"):
        pytest.skip("Optional Tesseract not installed")
    monkeypatch.setenv("TRACEPAPER_OCR", "1")
    original = fitz.open()
    p = original.new_page()
    p.insert_text((60, 100), "Chlorophyll absorbs light in plants.", fontsize=22)
    image = p.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    scanned = fitz.open()
    p = scanned.new_page()
    p.insert_image(p.rect, stream=image)
    paper = add(client, "scan.pdf", scanned.tobytes())
    assert paper["status"] == "ready", paper["error"]
    a = client.post("/api/ask", json={"question": "chlorophyll"}).json()
    assert a["sources"] and a["sources"][0]["page"] == 1


def gemini_response(claims=None, finish="STOP", **extra):
    import httpx, json

    data = {
        "candidates": [
            {
                "finishReason": finish,
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "claims": claims
                                    if claims is not None
                                    else [
                                        {
                                            "text": "Plants convert light into chemical energy.",
                                            "citations": [1],
                                        }
                                    ]
                                }
                            )
                        }
                    ]
                },
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 30,
            "thoughtsTokenCount": 12,
            "totalTokenCount": 142,
        },
        **extra,
    }
    return httpx.Response(
        200,
        json=data,
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
    )


def test_gemini_native_request_and_usage(client, monkeypatch):
    import json

    add(client)
    client.headers["X-Provider-Key"] = "test-gemini-placeholder"
    config = client.get("/api/config").json()
    assert (
        config["requires_user_key"] and config["models"]["gemini"] == "gemini-3.8-flash"
    )
    assert "test-gemini-placeholder" not in json.dumps(config)
    with patch("backend.main.httpx.Client") as provider:
        provider.return_value.__enter__.return_value.post.return_value = (
            gemini_response()
        )
        a = client.post("/api/ask", json={"question": "photosynthesis"}).json()
        args, kwargs = provider.return_value.__enter__.return_value.post.call_args
    assert (
        args[0]
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    )
    assert (
        "?" not in args[0]
        and kwargs["headers"]["x-goog-api-key"] == "test-gemini-placeholder"
    )
    assert kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"
    body = json.loads(kwargs["json"]["contents"][0]["parts"][0]["text"])
    assert body["question"] == "photosynthesis" and body["passages"][0]["id"] == 1
    assert (
        a["mode"] == "generated"
        and a["provider"] == "gemini"
        and a["claims"][0]["citations"] == [1]
    )
    assert a["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 30,
        "thinking_tokens": 12,
        "total_tokens": 142,
    }
    assert a["estimated_cost_usd"] is None


@pytest.mark.parametrize(
    "claims",
    [
        [{"text": "Made up", "citations": [999]}],
        [{"text": "Invalid ID type", "citations": [True]}],
        [],
    ],
)
def test_gemini_citation_validation(client, monkeypatch, claims):
    add(client)
    client.headers["X-Provider-Key"] = "test-placeholder"
    with patch("backend.main.httpx.Client") as provider:
        provider.return_value.__enter__.return_value.post.return_value = (
            gemini_response(claims)
        )
        a = client.post("/api/ask", json={"question": "photosynthesis"}).json()
    assert a["mode"] == "generated" and a["insufficient"] and not a["claims"]


@pytest.mark.parametrize(
    "failure",
    [
        "blocked",
        "truncated",
        "rate_limit",
        "invalid_json",
        "bad_shape",
        "missing_candidates",
    ],
)
def test_gemini_safe_fallback(client, monkeypatch, failure):
    import httpx

    add(client)
    client.headers["X-Provider-Key"] = "test-placeholder"
    response = gemini_response(
        finish="SAFETY"
        if failure == "blocked"
        else "MAX_TOKENS"
        if failure == "truncated"
        else "STOP"
    )
    if failure == "rate_limit":
        response = httpx.Response(
            429,
            json={"error": {"message": "quota exceeded"}},
            request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
        )
    elif failure in ("invalid_json", "bad_shape"):
        data = response.json()
        data["candidates"][0]["content"]["parts"][0]["text"] = (
            "not-json" if failure == "invalid_json" else '{"claims":[null]}'
        )
        response = httpx.Response(200, json=data, request=response.request)
    elif failure == "missing_candidates":
        response = httpx.Response(
            200,
            json={"promptFeedback": {"blockReason": "SAFETY"}},
            request=response.request,
        )
    with patch("backend.main.httpx.Client") as provider:
        provider.return_value.__enter__.return_value.post.return_value = response
        a = client.post("/api/ask", json={"question": "photosynthesis"}).json()
    assert a["mode"] == "extractive" and a["warning"] and a["claims"]
    assert a["estimated_cost_usd"] is None and a["provider"] is None


def test_server_keys_never_enable_generation(client, monkeypatch):
    add(client)
    for name in ("TRACEPAPER_GEMINI_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "owner-key-must-never-be-used")
    with patch("backend.main.httpx.Client") as provider:
        a = client.post("/api/ask", json={"question": "photosynthesis"}).json()
        provider.assert_not_called()
    assert a["mode"] == "extractive" and not a["warning"]
    config = client.get("/api/config").json()
    assert config["requires_user_key"] and "generation" not in config
    monkeypatch.setenv("TRACEPAPER_GEMINI_MODEL", "custom-gemini-model")
    assert client.get("/api/config").json()["models"]["gemini"] == "custom-gemini-model"


def test_each_request_uses_its_own_key_and_history_never_stores_it(client):
    add(client)
    with patch("backend.main.httpx.Client") as provider:
        transport = provider.return_value.__enter__.return_value
        transport.post.return_value = gemini_response()
        for key in ("visitor-one-fake-key", "visitor-two-fake-key"):
            r = client.post(
                "/api/ask",
                headers={"X-Provider-Key": key},
                json={"question": "photosynthesis"},
            )
            assert r.json()["mode"] == "generated"
            assert transport.post.call_args.kwargs["headers"]["x-goog-api-key"] == key
            assert key not in r.text
            history = client.get("/api/history/" + r.json()["id"])
            assert key not in history.text
        # Neither a later request nor another visitor inherits the previous credential.
        count = transport.post.call_count
        assert (
            client.post("/api/ask", json={"question": "photosynthesis"}).json()["mode"]
            == "extractive"
        )
        with TestClient(main.app) as other:
            assert (
                other.post("/api/ask", json={"question": "photosynthesis"}).json()[
                    "mode"
                ]
                == "extractive"
            )
        assert transport.post.call_count == count
    for path in main.DATA.glob("library.db*"):
        data = path.read_bytes()
        assert (
            b"visitor-one-fake-key" not in data and b"visitor-two-fake-key" not in data
        )


def test_key_errors_do_not_echo_credentials(client, caplog):
    add(client)
    key = "fake-key-not-to-be-logged"
    with patch("backend.main.httpx.Client", side_effect=RuntimeError(key)):
        r = client.post(
            "/api/ask",
            headers={"X-Provider-Key": key},
            json={"question": "photosynthesis"},
        )
    assert r.json()["mode"] == "extractive" and r.json()["warning"]
    assert key not in r.text and key not in caplog.text
    r = client.post(
        "/api/ask",
        headers={"X-Provider-Key": "x" * 5000},
        json={"question": "photosynthesis"},
    )
    assert r.status_code == 400 and "x" * 5000 not in r.text
    assert (
        client.post(
            "/api/ask", json={"question": "photosynthesis", "provider": "unknown"}
        ).status_code
        == 422
    )


def test_unicode_password_and_host_path_cannot_bypass_login(client, monkeypatch):
    monkeypatch.setenv("TRACEPAPER_PASSWORD", "pásswörd-研究")
    assert (
        client.post("/api/login", json={"password": "incorrect-研究"}).status_code
        == 401
    )
    assert (
        client.get(
            "/api/papers", headers={"Host": "testserver/api/health#"}
        ).status_code
        == 401
    )
    assert (
        client.post("/api/login", json={"password": "pásswörd-研究"}).status_code == 200
    )
    assert client.get("/api/papers").status_code == 200


def test_request_limits_apply_before_parsing_and_to_streams(client):
    r = client.post(
        "/api/papers",
        headers={
            "Content-Length": str(53 * 1024 * 1024),
            "Content-Type": "multipart/form-data; boundary=test",
        },
        content=b"x",
    )
    assert r.status_code == 413

    def chunks():
        yield b" " * (64 * 1024)
        yield b"{}"

    r = client.post(
        "/api/ask", headers={"Content-Type": "application/json"}, content=chunks()
    )
    assert r.status_code == 413
    assert (
        client.post(
            "/api/login", headers={"Content-Length": "-1"}, content=b"{}"
        ).status_code
        == 400
    )


def test_parser_timeout_is_recorded_without_breaking_other_requests(client):
    import subprocess

    with patch(
        "backend.main.subprocess.run",
        side_effect=subprocess.TimeoutExpired("parser", 180),
    ):
        p = add(client)
    assert p["status"] == "failed" and "180 seconds" in p["error"]
    assert client.get("/api/health").status_code == 200


def test_encrypted_pdf_has_actionable_error(client):
    doc = fitz.open()
    doc.new_page().insert_text((60, 60), "Encrypted research document")
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-test",
        user_pw="reader-test",
    )
    p = add(client, "locked.pdf", data)
    assert p["status"] == "failed" and "Password-protected" in p["error"]


def test_interrupted_indexing_is_recovered_on_startup(client):
    paper = add(client)
    with main.db() as c:
        c.execute("UPDATE papers SET status='indexing' WHERE id=?", (paper["id"],))
    main.initialize()
    for _ in range(150):
        row = client.get("/api/papers").json()["items"][0]
        if row["status"] == "ready":
            break
        time.sleep(0.03)
    assert row["status"] == "ready"
    answer = client.post("/api/ask", json={"question": "chlorophyll"}).json()
    assert answer["sources"][0]["page"] == 2
