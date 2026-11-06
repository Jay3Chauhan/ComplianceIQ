"""
Chat orchestration: conversation handling + RAG pipeline + persistence + logging.

SSE protocol for /api/v1/chat/stream (each frame: `event: <type>` + JSON `data`):
  conversation  {conversation_id, user_message_id}            first frame (when saving)
  status        {stage, message}
  retrieval     {mode, grounded, gate_score, standalone_question, sources, timings}
  token         {content}
  verification  {status, score, ..., final}
  revision      {answer, mode}                                  replaces streamed text
  done          {message_id, mode, answer, confidence, model, latency_ms}
  error         {code, message}
"""

import json
from collections.abc import Iterator

from loguru import logger

from api.context import get_request_id
from api.errors import APIError
from api.schemas import ChatRequest
from db import repository as repo
from rag.pipeline import RAGRequest, RAGResponse
from rag import pipeline


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data}, ensure_ascii=False)}\n\n"


def _prepare(req: ChatRequest, user_id: str) -> tuple[str | None, list[dict] | None]:
    """Resolves the conversation and history. Returns (conversation_id, history)."""
    if req.conversation_id:
        if not repo.conversation_exists(user_id, req.conversation_id):
            raise APIError(404, "conversation_not_found", "Conversation not found.")
        return req.conversation_id, repo.history_for_rag(req.conversation_id)
    history = [t.model_dump() for t in req.history] if req.history else None
    if req.save:
        conv = repo.create_conversation(user_id, category=req.category, answer_mode=req.answer_mode)
        return conv["id"], history
    return None, history


def _rag_request(req: ChatRequest, history: list[dict] | None) -> RAGRequest:
    return RAGRequest(
        question=req.question,
        category=req.category,
        top_k=req.top_k,
        answer_mode=req.answer_mode,
        history=history,
        verify=req.verify,
    )


def _log(user_id: str, conversation_id: str | None, message_id: str | None, endpoint: str,
         req: ChatRequest, **fields) -> None:
    try:
        repo.log_query(
            request_id=get_request_id(),
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            endpoint=endpoint,
            question=req.question,
            category=req.category,
            answer_mode=req.answer_mode,
            **fields,
        )
    except Exception as e:
        logger.warning(f"Query log failed: {e}")


def _top_sources(sources: list[dict]) -> list[dict]:
    return [{"doc_id": s["doc_id"], "page": s["page_number"], "score": s["relevance_score"]} for s in sources[:3]]


def run_chat(req: ChatRequest, user_id: str) -> dict:
    conversation_id, history = _prepare(req, user_id)
    user_msg = repo.add_message(conversation_id, "user", req.question) if conversation_id else None

    try:
        result: RAGResponse = pipeline.answer(_rag_request(req, history))
    except Exception as e:
        _log(user_id, conversation_id, None, "chat", req, error=str(e)[:500])
        if conversation_id:
            repo.add_message(conversation_id, "assistant", "", status="error")
        raise

    assistant_msg = None
    if conversation_id:
        assistant_msg = repo.add_message(
            conversation_id, "assistant", result.answer,
            mode=result.mode, sources=result.sources, verification=result.verification,
            confidence=result.confidence, revised=result.revised,
            standalone_question=result.standalone_question, model=result.model, latency_ms=result.latency_ms,
        )
    ver = result.verification or {}
    _log(
        user_id, conversation_id, assistant_msg["id"] if assistant_msg else None, "chat", req,
        standalone_question=result.standalone_question, mode=result.mode, grounded=result.grounded,
        gate_score=result.gate_score, top_sources=_top_sources(result.sources),
        verification_status=ver.get("status"), verification_score=ver.get("score"), revised=result.revised,
        confidence=result.confidence, model=result.model, latency_ms=result.latency_ms, timings=result.timings,
    )
    return {
        "conversation_id": conversation_id,
        "message_id": assistant_msg["id"] if assistant_msg else None,
        "user_message_id": user_msg["id"] if user_msg else None,
        "answer": result.answer,
        "mode": result.mode,
        "grounded": result.grounded,
        "gate_score": result.gate_score,
        "confidence": result.confidence,
        "sources": result.sources,
        "verification": result.verification,
        "revised": result.revised,
        "standalone_question": result.standalone_question,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "timings": result.timings,
    }


def prepare_stream(req: ChatRequest, user_id: str) -> tuple[str | None, dict | None, list[dict] | None]:
    """Runs before the response starts so 404s are real HTTP errors, not stream events."""
    conversation_id, history = _prepare(req, user_id)
    user_msg = repo.add_message(conversation_id, "user", req.question) if conversation_id else None
    return conversation_id, user_msg, history


def stream_chat(req: ChatRequest, user_id: str, conversation_id: str | None, user_msg: dict | None,
                history: list[dict] | None) -> Iterator[str]:
    if conversation_id:
        yield sse("conversation", {"conversation_id": conversation_id, "user_message_id": user_msg["id"] if user_msg else None})

    state: dict = {"text": [], "sources": [], "mode": None, "verification": None, "revised": False,
                   "retrieval": {}, "done": None, "error": None}
    try:
        for event in pipeline.stream(_rag_request(req, history)):
            etype = event["type"]
            data = {k: v for k, v in event.items() if k != "type"}
            if etype == "token":
                state["text"].append(event["content"])
            elif etype == "retrieval":
                state["sources"], state["mode"] = event["sources"], event["mode"]
                state["retrieval"] = event
            elif etype == "revision":
                state["text"], state["revised"] = [event["answer"]], True
                state["mode"] = event.get("mode", state["mode"])
                if "sources" in event:
                    state["sources"] = event["sources"]
            elif etype == "verification" and event.get("final"):
                state["verification"] = {k: v for k, v in data.items() if k != "final"}
            elif etype == "error":
                state["error"] = event
            elif etype == "done":
                state["done"] = event
                continue  # emitted below with the persisted message id
            yield sse(etype, data)
    finally:
        message_id = _persist_stream(req, user_id, conversation_id, state)

    if state["done"]:
        done = {k: v for k, v in state["done"].items() if k != "type"}
        yield sse("done", {**done, "message_id": message_id, "conversation_id": conversation_id})


def _persist_stream(req: ChatRequest, user_id: str, conversation_id: str | None, state: dict) -> str | None:
    done = state["done"] or {}
    text = done.get("answer") or "".join(state["text"]).strip()
    failed = state["error"] is not None or not state["done"]
    message_id = None
    try:
        if conversation_id:
            msg = repo.add_message(
                conversation_id, "assistant", text,
                status="error" if failed else "complete",
                mode=done.get("mode") or state["mode"],
                sources=state["sources"] if (done.get("mode") or state["mode"]) == "regulatory" else [],
                verification=state["verification"],
                confidence=done.get("confidence"),
                revised=state["revised"],
                standalone_question=state["retrieval"].get("standalone_question"),
                model=done.get("model"),
                latency_ms=done.get("latency_ms"),
            )
            message_id = msg["id"]
        ver = state["verification"] or {}
        _log(
            user_id, conversation_id, message_id, "chat_stream", req,
            standalone_question=state["retrieval"].get("standalone_question"),
            mode=done.get("mode") or state["mode"],
            grounded=state["retrieval"].get("grounded"),
            gate_score=state["retrieval"].get("gate_score"),
            top_sources=_top_sources(state["sources"]),
            verification_status=ver.get("status"), verification_score=ver.get("score"),
            revised=state["revised"], confidence=done.get("confidence"), model=done.get("model"),
            latency_ms=done.get("latency_ms"), timings=state["retrieval"].get("timings"),
            error=(state["error"] or {}).get("code") if failed else None,
        )
    except Exception as e:
        logger.warning(f"Persisting streamed answer failed: {e}")
    return message_id
