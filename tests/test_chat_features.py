"""Chat reliability features: stop, busy conversations, regenerate, edit, follow-ups, export, heartbeats."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import chat as chat_service
from api.services.runs import runs
from config import settings
from rag import pipeline
from rag.pipeline import RAGResponse, build_sources
from tests.conftest import API_HEADERS

ANSWER = "High risk customers must update KYC every two years [1]."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def live_url():
    """Real uvicorn server: TestClient buffers whole responses, so mid-stream behaviour needs real HTTP."""
    import socket
    import threading

    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _clean_runs():
    runs.clear()
    yield
    runs.clear()


def _events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


@pytest.fixture
def fake_rag(monkeypatch, sample_chunks):
    """Pipeline double. `config` controls the stream: token delay, token count, mode, mid-stream error."""
    seen: list = []
    config = {"delay": 0.0, "tokens": 2, "mode": "regulatory", "fail": False}

    def answer(req):
        seen.append(req)
        return RAGResponse(answer=ANSWER, mode=config["mode"], sources=build_sources(sample_chunks),
                           standalone_question=req.question, grounded=True, gate_score=0.9,
                           confidence="high", model="fake", latency_ms=5, timings={})

    def stream(req):
        seen.append(req)
        yield {"type": "status", "stage": "searching", "message": "Searching"}
        yield {"type": "retrieval", "mode": config["mode"], "grounded": True, "gate_score": 0.9,
               "standalone_question": req.question, "sources": build_sources(sample_chunks), "timings": {}}
        for i in range(config["tokens"]):
            if config["delay"]:
                time.sleep(config["delay"])
            yield {"type": "token", "content": f"part{i} "}
        if config["fail"]:
            yield {"type": "error", "code": "rate_limited", "message": "The language model is rate limited."}
            return
        yield {"type": "done", "mode": config["mode"], "answer": ANSWER, "confidence": "high",
               "model": "fake", "latency_ms": 7}

    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "stream", stream)
    return seen, config


@pytest.fixture
def fake_followups(monkeypatch):
    monkeypatch.setattr(settings, "enable_followups", True)
    monkeypatch.setattr(settings, "enable_llm_titles", True)
    calls: list = []

    def suggest(question, answer, want_followups=True, want_title=False):
        calls.append({"question": question, "want_title": want_title})
        return {"followups": ["What is the deadline for low risk customers?"] if want_followups else [],
                "title": "KYC Update Timelines" if want_title else None}

    monkeypatch.setattr(chat_service.followup_llm, "suggest", suggest)
    return calls


def _ask(client, question: str, **extra) -> dict:
    res = client.post("/api/v1/chat", json={"question": question, **extra}, headers=API_HEADERS)
    assert res.status_code == 200, res.text
    return res.json()


def _conversation(client, conversation_id: str) -> dict:
    return client.get(f"/api/v1/conversations/{conversation_id}", headers=API_HEADERS).json()


def _wait_idle(conversation_id: str, timeout: float = 5.0) -> None:
    end = time.time() + timeout
    while runs.is_active(conversation_id) and time.time() < end:
        time.sleep(0.02)


# ── Stream completion, follow-ups, titles ────────────────────────────────────

def test_stream_done_status_followups_and_title(client, fake_rag, fake_followups) -> None:
    with client.stream("POST", "/api/v1/chat/stream", json={"question": "Periodic KYC updation timelines?"},
                       headers=API_HEADERS) as res:
        events = _events("".join(res.iter_text()))
    types = [e["type"] for e in events]
    assert types.index("followups") < types.index("title") < types.index("done") == len(types) - 1
    done = events[-1]
    assert done["status"] == "complete" and done["answer"] == ANSWER

    conv = _conversation(client, done["conversation_id"])
    assert conv["title"] == "KYC Update Timelines"
    assert conv["streaming"] is False
    assert conv["messages"][-1]["followups"] == ["What is the deadline for low risk customers?"]
    assert fake_followups[0]["want_title"] is True


def test_stream_error_ends_with_done_and_can_be_retried(client, fake_rag) -> None:
    fake_rag[1]["fail"] = True
    with client.stream("POST", "/api/v1/chat/stream", json={"question": "Periodic KYC updation timelines?"},
                       headers=API_HEADERS) as res:
        events = _events("".join(res.iter_text()))
    assert [e["type"] for e in events][-2:] == ["error", "done"]
    done = events[-1]
    assert done["status"] == "error" and done["message_id"] and done["answer"] == "part0 part1"
    saved = client.get(f"/api/v1/messages/{done['message_id']}", headers=API_HEADERS).json()
    assert saved["status"] == "error"

    fake_rag[1]["fail"] = False
    res = client.post(f"/api/v1/messages/{done['message_id']}/regenerate", headers=API_HEADERS)
    retry = _events(res.text)[-1]
    assert retry["status"] == "complete"
    messages = _conversation(client, done["conversation_id"])["messages"]
    assert [(m["role"], m["status"]) for m in messages] == [("user", "complete"), ("assistant", "complete")]


def test_title_only_generated_for_first_exchange(client, fake_rag, fake_followups) -> None:
    body = _ask(client, "What is V-CIP?")
    assert body["title"] == "KYC Update Timelines" and body["followups"]
    _ask(client, "Who can perform V-CIP?", conversation_id=body["conversation_id"])
    assert [c["want_title"] for c in fake_followups] == [True, False]


def test_user_renamed_title_is_not_overwritten(client, fake_rag, fake_followups) -> None:
    conv = client.post("/api/v1/conversations", json={"title": "My audit notes"}, headers=API_HEADERS).json()
    body = _ask(client, "What is CKYCR?", conversation_id=conv["id"])
    assert body["title"] is None
    assert _conversation(client, conv["id"])["title"] == "My audit notes"


def test_not_found_suggests_starter_questions(client, fake_rag, fake_followups) -> None:
    fake_rag[1]["mode"] = "not_found"
    body = _ask(client, "What is the GST rate on restaurants?", category="SEBI")
    assert body["mode"] == "not_found"
    assert len(body["followups"]) == 3 and all("?" in q for q in body["followups"])
    assert fake_followups == []  # no LLM call


def test_followups_can_be_disabled_per_request(client, fake_rag, fake_followups) -> None:
    body = _ask(client, "What is the KFS?", followups=False)
    assert body["followups"] == []


# ── Heartbeat ────────────────────────────────────────────────────────────────

def test_heartbeat_comments_during_silence(client, fake_rag, monkeypatch) -> None:
    monkeypatch.setattr(settings, "sse_heartbeat_seconds", 0.05)
    fake_rag[1].update(delay=0.25, tokens=2)
    with client.stream("POST", "/api/v1/chat/stream", json={"question": "Slow question please"},
                       headers=API_HEADERS) as res:
        body = "".join(res.iter_text())
    assert ": ping" in body
    assert _events(body)[-1]["type"] == "done"


# ── Stop and busy conversations ──────────────────────────────────────────────

def _live_events(base: str, path: str, payload: dict, on_event) -> list[dict]:
    """Streams SSE from the live server, calling on_event(event, events) for every data frame."""
    import httpx

    events: list[dict] = []
    with httpx.stream("POST", base + path, json=payload, headers=API_HEADERS, timeout=30) as res:
        assert res.status_code == 200, res.read()
        for line in res.iter_lines():
            if not line.startswith("data: "):
                continue
            events.append(json.loads(line[6:]))
            if on_event(events[-1], events) is False:
                break
    return events


def test_stop_saves_partial_answer(client, live_url, fake_rag) -> None:
    import httpx

    fake_rag[1].update(delay=0.02, tokens=500)

    def on_event(event, events):
        if event["type"] == "token" and event["content"] == "part2 ":
            cid = events[0]["conversation_id"]
            stop = httpx.post(f"{live_url}/api/v1/conversations/{cid}/stop", headers=API_HEADERS)
            assert stop.status_code == 200 and stop.json()["stopped"] is True

    events = _live_events(live_url, "/api/v1/chat/stream", {"question": "A long answer please"}, on_event)
    done = events[-1]
    assert done["type"] == "done" and done["status"] == "stopped"
    assert done["answer"].startswith("part0 part1 part2") and len(done["answer"].split()) < 100
    conv = _conversation(client, done["conversation_id"])
    assert conv["messages"][-1]["status"] == "stopped" and conv["streaming"] is False


def test_stop_when_idle_reports_false(client, fake_rag) -> None:
    body = _ask(client, "What is a consent artefact?")
    res = client.post(f"/api/v1/conversations/{body['conversation_id']}/stop", headers=API_HEADERS)
    assert res.json() == {"conversation_id": body["conversation_id"], "stopped": False}


def test_busy_conversation_rejects_second_message(client, live_url, fake_rag) -> None:
    import httpx

    body = _ask(client, "What is an NBFC-AA?")
    cid = body["conversation_id"]
    fake_rag[1].update(delay=0.02, tokens=500)
    checked: list[bool] = []

    def on_event(event, events):
        if event["type"] == "token" and not checked:
            busy = httpx.post(f"{live_url}/api/v1/chat", json={"question": "Another one", "conversation_id": cid},
                              headers=API_HEADERS)
            assert busy.status_code == 409 and busy.json()["error"]["code"] == "conversation_busy"
            assert _conversation(client, cid)["streaming"] is True
            httpx.post(f"{live_url}/api/v1/conversations/{cid}/stop", headers=API_HEADERS)
            checked.append(True)

    events = _live_events(live_url, "/api/v1/chat/stream", {"question": "Tell me more", "conversation_id": cid},
                          on_event)
    assert checked and events[-1]["status"] == "stopped"
    _wait_idle(cid)
    assert _ask(client, "Now it works", conversation_id=cid)["mode"] == "regulatory"


def test_real_http_disconnect_stops_generation(client, live_url, fake_rag) -> None:
    fake_rag[1].update(delay=0.02, tokens=500)
    events = _live_events(live_url, "/api/v1/chat/stream", {"question": "I will hang up early"},
                          lambda event, _: event["type"] != "token")
    cid = events[0]["conversation_id"]
    _wait_idle(cid)
    assert not runs.is_active(cid)
    last = _conversation(client, cid)["messages"][-1]
    assert last["status"] == "stopped" and len(last["content"].split()) < 100


def test_client_disconnect_cancels_generation(fake_rag) -> None:
    """Relay cleanup (what Starlette does on disconnect) must cancel the worker."""
    import asyncio

    from api.schemas import ChatRequest

    fake_rag[1].update(delay=0.02, tokens=500)
    job = chat_service.prepare_chat(ChatRequest(question="Disconnect test"), "user-a", "chat_stream")

    async def read_then_leave() -> None:
        relay = chat_service.start_stream(job)
        async for frame in relay:
            if '"type": "token"' in frame:
                break
        await relay.aclose()

    asyncio.run(read_then_leave())
    _wait_idle(job.conversation_id)
    from db import repository as repo
    last = repo.get_conversation("user-a", job.conversation_id)["messages"][-1]
    assert last["status"] == "stopped" and len(last["content"].split()) < 100


# ── Regenerate and edit ──────────────────────────────────────────────────────

def test_regenerate_replaces_answer(client, fake_rag) -> None:
    first = _ask(client, "What are KYC timelines?")
    second = _ask(client, "And for medium risk?", conversation_id=first["conversation_id"])

    with client.stream("POST", f"/api/v1/messages/{first['message_id']}/regenerate",
                       json={"answer_mode": "regulatory"}, headers=API_HEADERS) as res:
        assert res.status_code == 200
        events = _events("".join(res.iter_text()))
    assert events[0]["type"] == "conversation" and events[-1]["status"] == "complete"
    assert events[0]["user_message_id"] == first["user_message_id"]

    conv = _conversation(client, first["conversation_id"])
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]  # later exchange removed
    assert conv["message_count"] == 2 and conv["answer_mode"] == "regulatory"
    assert all(m["id"] != second["message_id"] for m in conv["messages"])
    assert fake_rag[0][-1].question == "What are KYC timelines?" and fake_rag[0][-1].history is None


def test_regenerate_rejects_user_messages_and_unknown_ids(client, fake_rag) -> None:
    body = _ask(client, "What is FLDG?")
    res = client.post(f"/api/v1/messages/{body['user_message_id']}/regenerate", headers=API_HEADERS)
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_message"
    assert client.post("/api/v1/messages/nope/regenerate", headers=API_HEADERS).status_code == 404
    other = {**API_HEADERS, "X-User-Id": "user-b"}
    assert client.post(f"/api/v1/messages/{body['message_id']}/regenerate", headers=other).status_code == 404
    assert not runs.is_active(body["conversation_id"])  # slot released after errors


def test_edit_replaces_question_and_drops_later_messages(client, fake_rag) -> None:
    first = _ask(client, "What is the KYC update period?")
    _ask(client, "And for low risk?", conversation_id=first["conversation_id"])
    _ask(client, "Any penalty?", conversation_id=first["conversation_id"])

    conv = _conversation(client, first["conversation_id"])
    second_user = conv["messages"][2]
    with client.stream("POST", f"/api/v1/messages/{second_user['id']}/edit",
                       json={"question": "And for medium risk customers?"}, headers=API_HEADERS) as res:
        events = _events("".join(res.iter_text()))
    assert events[-1]["status"] == "complete"

    conv = _conversation(client, first["conversation_id"])
    assert [m["content"] for m in conv["messages"] if m["role"] == "user"] == [
        "What is the KYC update period?", "And for medium risk customers?"]
    assert len(conv["messages"]) == 4 and conv["message_count"] == 4
    assert fake_rag[0][-1].history == [{"question": "What is the KYC update period?", "answer": ANSWER}]


def test_editing_first_question_updates_default_title(client, fake_rag) -> None:
    first = _ask(client, "What is V-CIP")
    with client.stream("POST", f"/api/v1/messages/{first['user_message_id']}/edit",
                       json={"question": "What is Video KYC?"}, headers=API_HEADERS) as res:
        "".join(res.iter_text())
    assert _conversation(client, first["conversation_id"])["title"] == "What is Video KYC?"


def test_edit_rejects_assistant_messages(client, fake_rag) -> None:
    body = _ask(client, "What is a LSP?")
    res = client.post(f"/api/v1/messages/{body['message_id']}/edit", json={"question": "changed question"},
                      headers=API_HEADERS)
    assert res.status_code == 400


# ── Settings, lookup, export, delete ─────────────────────────────────────────

def test_conversation_remembers_last_settings(client, fake_rag) -> None:
    body = _ask(client, "What is an FIP?", category="AA")
    _ask(client, "What is an FIU?", conversation_id=body["conversation_id"], category="AA",
         answer_mode="regulatory")
    conv = _conversation(client, body["conversation_id"])
    assert conv["category"] == "AA" and conv["answer_mode"] == "regulatory"


def test_get_message(client, fake_rag) -> None:
    body = _ask(client, "What is swing pricing?")
    msg = client.get(f"/api/v1/messages/{body['message_id']}", headers=API_HEADERS).json()
    assert msg["role"] == "assistant" and msg["status"] == "complete" and msg["sources"][0]["id"] == 1
    assert client.get(f"/api/v1/messages/{body['message_id']}",
                      headers={**API_HEADERS, "X-User-Id": "user-b"}).status_code == 404


def test_export_markdown_and_json(client, fake_rag) -> None:
    body = _ask(client, "What is the KYC updation timeline?")
    cid = body["conversation_id"]
    md = client.get(f"/api/v1/conversations/{cid}/export", headers=API_HEADERS)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert 'filename="complianceiq-what-is-the-kyc-updation-timeline.md"' in md.headers["content-disposition"]
    assert "### Question" in md.text and "**Sources**" in md.text and "RBI/DBR/2016" in md.text

    js = client.get(f"/api/v1/conversations/{cid}/export?format=json", headers=API_HEADERS)
    assert js.json()["id"] == cid and len(js.json()["messages"]) == 2


def test_delete_conversation_while_streaming(client, live_url, fake_rag) -> None:
    import httpx

    fake_rag[1].update(delay=0.02, tokens=500)
    deleted: list[bool] = []

    def on_event(event, events):
        if event["type"] == "token" and not deleted:
            cid = events[0]["conversation_id"]
            assert httpx.delete(f"{live_url}/api/v1/conversations/{cid}", headers=API_HEADERS).status_code == 204
            deleted.append(True)

    events = _live_events(live_url, "/api/v1/chat/stream", {"question": "Delete me mid answer"}, on_event)
    cid = events[0]["conversation_id"]
    assert events[-1]["type"] == "done" and events[-1]["status"] == "stopped"
    _wait_idle(cid)
    assert client.get(f"/api/v1/conversations/{cid}", headers=API_HEADERS).status_code == 404
