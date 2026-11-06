"""API tests with the RAG pipeline mocked (no network, temp SQLite)."""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from rag import pipeline
from rag.pipeline import RAGResponse, build_sources
from tests.conftest import API_HEADERS

ANSWER = "Periodic updation is required every two years for high risk customers [1]."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_rag(monkeypatch, sample_chunks):
    seen: list = []

    def answer(req):
        seen.append(req)
        return RAGResponse(
            answer=ANSWER, mode="regulatory", sources=build_sources(sample_chunks),
            standalone_question=req.question, grounded=True, gate_score=0.9,
            verification={"status": "verified", "score": 1.0, "method": "rules", "claims_checked": 1,
                          "supported": 1, "unsupported_claims": [], "uncited_claims": [],
                          "invalid_citations": [], "unsupported_numbers": [], "citation_issues": []},
            confidence="high", model="fake", latency_ms=12, timings={"search_ms": 3},
        )

    def stream(req):
        seen.append(req)
        yield {"type": "status", "stage": "searching", "message": "Searching"}
        yield {"type": "retrieval", "mode": "regulatory", "grounded": True, "gate_score": 0.9,
               "standalone_question": req.question, "sources": build_sources(sample_chunks), "timings": {}}
        for part in ("Periodic updation ", "is required [1]."):
            yield {"type": "token", "content": part}
        yield {"type": "verification", "status": "verified", "score": 1.0, "method": "rules", "final": True}
        yield {"type": "done", "mode": "regulatory", "answer": "Periodic updation is required [1].",
               "confidence": "high", "model": "fake", "latency_ms": 20}

    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "stream", stream)
    return seen


def _sse_events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ") and line[6:] != "[DONE]"]


# ── Health / meta / auth ─────────────────────────────────────────────────────

def test_health_is_public_and_has_request_id(client) -> None:
    res = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-123"})
    assert res.status_code == 200 and res.json()["status"] == "ok"
    assert res.headers["x-request-id"] == "test-request-123"


def test_ready_reports_checks(client) -> None:
    res = client.get("/api/v1/ready")
    assert res.status_code in (200, 503)
    assert {"qdrant", "database", "models", "llm"} <= set(res.json()["checks"])


def test_protected_endpoints_require_api_key(client) -> None:
    res = client.get("/api/v1/meta")
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "unauthorized" and err["request_id"]


def test_meta_and_suggestions(client) -> None:
    meta = client.get("/api/v1/meta", headers=API_HEADERS).json()
    assert {c["id"] for c in meta["categories"]} == {"ALL", "RBI", "SEBI", "AA"}
    assert meta["features"]["verification"] is True
    sugg = client.get("/api/v1/suggestions?category=AA&limit=2", headers=API_HEADERS).json()
    assert len(sugg["suggestions"]) == 2


def test_validation_error_envelope(client) -> None:
    res = client.post("/api/v1/chat", json={"question": "  "}, headers=API_HEADERS)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
    assert res.json()["error"]["details"][0]["field"] == "question"


def test_invalid_user_id_rejected(client) -> None:
    res = client.get("/api/v1/conversations", headers={**API_HEADERS, "X-User-Id": "bad id with spaces"})
    assert res.status_code == 400


# ── Chat + conversations ─────────────────────────────────────────────────────

def test_chat_creates_conversation_and_persists(client, fake_rag) -> None:
    res = client.post("/api/v1/chat", json={"question": "How often is periodic KYC updation?"}, headers=API_HEADERS)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "regulatory" and body["confidence"] == "high"
    assert body["sources"][0]["id"] == 1
    conv_id = body["conversation_id"]

    conv = client.get(f"/api/v1/conversations/{conv_id}", headers=API_HEADERS).json()
    assert conv["title"] == "How often is periodic KYC updation?"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["verification"]["status"] == "verified"

    # follow-up uses stored history
    client.post("/api/v1/chat", json={"question": "And for low risk?", "conversation_id": conv_id}, headers=API_HEADERS)
    assert fake_rag[-1].history == [{"question": "How often is periodic KYC updation?", "answer": ANSWER}]


def test_conversations_are_scoped_per_user(client, fake_rag) -> None:
    conv_id = client.post("/api/v1/chat", json={"question": "What is V-CIP under KYC?"},
                          headers=API_HEADERS).json()["conversation_id"]
    other = {**API_HEADERS, "X-User-Id": "user-b"}
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=other).status_code == 404
    res = client.post("/api/v1/chat", json={"question": "continue this", "conversation_id": conv_id}, headers=other)
    assert res.status_code == 404 and res.json()["error"]["code"] == "conversation_not_found"


def test_conversation_list_update_delete(client, fake_rag) -> None:
    conv = client.post("/api/v1/conversations", json={"title": "Scratch"}, headers=API_HEADERS).json()
    listing = client.get("/api/v1/conversations?q=Scratch", headers=API_HEADERS).json()
    assert any(c["id"] == conv["id"] for c in listing["items"])

    patched = client.patch(f"/api/v1/conversations/{conv['id']}", json={"pinned": True, "title": "Renamed"},
                           headers=API_HEADERS).json()
    assert patched["pinned"] and patched["title"] == "Renamed"

    assert client.delete(f"/api/v1/conversations/{conv['id']}", headers=API_HEADERS).status_code == 204
    assert client.get(f"/api/v1/conversations/{conv['id']}", headers=API_HEADERS).status_code == 404


def test_stateless_chat_does_not_persist(client, fake_rag) -> None:
    body = client.post("/api/v1/chat", json={"question": "What is CKYCR?", "save": False,
                                             "history": [{"question": "q", "answer": "a"}]},
                       headers=API_HEADERS).json()
    assert body["conversation_id"] is None and body["message_id"] is None
    assert fake_rag[-1].history == [{"question": "q", "answer": "a"}]


def test_feedback_roundtrip(client, fake_rag) -> None:
    body = client.post("/api/v1/chat", json={"question": "What is the KFS?"}, headers=API_HEADERS).json()
    mid = body["message_id"]
    res = client.put(f"/api/v1/messages/{mid}/feedback",
                     json={"rating": -1, "reasons": ["wrong_citation"], "comment": "page off"}, headers=API_HEADERS)
    assert res.status_code == 200 and res.json()["rating"] == -1

    conv = client.get(f"/api/v1/conversations/{body['conversation_id']}", headers=API_HEADERS).json()
    assert conv["messages"][1]["feedback"]["reasons"] == ["wrong_citation"]

    assert client.put(f"/api/v1/messages/{body['user_message_id']}/feedback", json={"rating": 1},
                      headers=API_HEADERS).status_code == 404
    assert client.delete(f"/api/v1/messages/{mid}/feedback", headers=API_HEADERS).status_code == 204


def test_chat_stream_events_and_persistence(client, fake_rag) -> None:
    with client.stream("POST", "/api/v1/chat/stream", json={"question": "Periodic updation rules?"},
                       headers=API_HEADERS) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        body = "".join(res.iter_text())
    events = _sse_events(body)
    types = [e["type"] for e in events]
    assert types[0] == "conversation"
    assert types[-1] == "done"
    assert "retrieval" in types and "token" in types and "verification" in types
    done = events[-1]
    assert done["message_id"] and done["conversation_id"] == events[0]["conversation_id"]

    conv = client.get(f"/api/v1/conversations/{done['conversation_id']}", headers=API_HEADERS).json()
    assistant = conv["messages"][-1]
    assert assistant["content"] == "Periodic updation is required [1]."
    assert assistant["status"] == "complete" and assistant["verification"]["status"] == "verified"


def test_stream_unknown_conversation_is_http_404(client, fake_rag) -> None:
    res = client.post("/api/v1/chat/stream", json={"question": "hello there", "conversation_id": "nope"},
                      headers=API_HEADERS)
    assert res.status_code == 404


# ── Admin ────────────────────────────────────────────────────────────────────

def test_admin_requires_admin_key(client) -> None:
    assert client.get("/api/v1/admin/jobs", headers=API_HEADERS).status_code == 401
    res = client.get("/api/v1/admin/jobs", headers={**API_HEADERS, "X-Admin-Key": "admin-key"})
    assert res.status_code == 200


def test_admin_upload_rejects_non_pdf(client) -> None:
    res = client.post(
        "/api/v1/admin/documents",
        headers={**API_HEADERS, "X-Admin-Key": "admin-key"},
        data={"name": "Not a PDF", "category": "RBI"},
        files={"file": ("evil.pdf", b"MZ not a pdf", "application/pdf")},
    )
    assert res.status_code == 415


# ── Legacy ───────────────────────────────────────────────────────────────────

def test_legacy_query_and_stream(client, fake_rag) -> None:
    res = client.post("/api/query", json={"question": "Periodic updation rules?"}, headers=API_HEADERS)
    assert res.status_code == 200
    assert res.json()["mode"] == "regulatory" and res.json()["chunks_used"] == 2

    with client.stream("POST", "/api/query/stream", json={"question": "Periodic updation rules?"},
                       headers=API_HEADERS) as stream:
        body = "".join(stream.iter_text())
    types = [e["type"] for e in _sse_events(body)]
    assert "meta" in types and "token" in types and types[-1] == "status"
    assert body.rstrip().endswith("data: [DONE]")


def test_legacy_query_validation(client) -> None:
    assert client.post("/api/query", json={"question": "hi"}, headers=API_HEADERS).status_code == 422
