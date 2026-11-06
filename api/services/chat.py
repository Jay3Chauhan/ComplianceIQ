"""
Chat orchestration: conversation handling, RAG pipeline, persistence, logging.

Each answer runs as a job:
  prepare_*()   validates and mutates the conversation *before* the HTTP response
                starts (so 404/409 are real HTTP errors) and reserves the
                conversation's run slot (one answer at a time per conversation).
  start_stream() runs the job in a worker thread. The worker owns persistence and
                releases the slot, so an answer is saved even if nobody is listening.
                The SSE relay sends heartbeats and cancels the job when the client
                disconnects; POST /conversations/{id}/stop cancels it explicitly.

SSE protocol (each frame: `event: <type>` + JSON `data` that repeats `type`):
  conversation  {conversation_id, user_message_id}            first frame (saved chats)
  status        {stage, message}
  retrieval     {mode, grounded, gate_score, standalone_question, sources, timings}
  token         {content}
  revision      {answer, mode, reason, sources?}              replaces the streamed text; later tokens append
                reason: format | repair | not_found | general_fallback (answer "" then a general answer streams)
  verification  {status, score, ..., final}
  followups     {followups: [str]}
  title         {conversation_id, title}
  error         {code, message}                               no more content; `done` follows
  done          {status: complete|stopped|error, message_id, conversation_id, mode, answer,
                 confidence, model, latency_ms}                always the last frame
Comment lines (`: ping`) are heartbeats and carry no data.
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from loguru import logger

from api.context import get_request_id
from api.errors import APIError
from api.schemas import ChatRequest, EditRequest, RegenerateRequest
from api.services.runs import runs
from config import settings
from db import repository as repo
from llm import followups as followup_llm
from rag import pipeline
from rag.pipeline import RAGRequest
from rag.suggestions import starter_questions

_END = object()


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data}, ensure_ascii=False)}\n\n"


@dataclass
class ChatJob:
    user_id: str
    endpoint: str
    question: str
    category: str
    answer_mode: str
    rag: RAGRequest
    conversation_id: str | None
    user_message: dict | None
    want_title: bool
    want_followups: bool
    request_id: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)


# ── Preparation (runs before the response starts) ────────────────────────────

def _job(user_id: str, endpoint: str, question: str, category: str, answer_mode: str, top_k: int | None,
         verify: bool | None, history: list[dict] | None, conversation_id: str | None, user_message: dict | None,
         want_title: bool, want_followups: bool, cancel: threading.Event) -> ChatJob:
    return ChatJob(
        user_id=user_id, endpoint=endpoint, question=question, category=category, answer_mode=answer_mode,
        rag=RAGRequest(question=question, category=category, top_k=top_k, answer_mode=answer_mode,
                       history=history or None, verify=verify),
        conversation_id=conversation_id, user_message=user_message, want_title=want_title,
        want_followups=want_followups, request_id=get_request_id(), cancel=cancel,
    )


def prepare_chat(req: ChatRequest, user_id: str, endpoint: str) -> ChatJob:
    if req.conversation_id:
        conv = repo.get_conversation(user_id, req.conversation_id, with_messages=False)
        if not conv:
            raise APIError(404, "conversation_not_found", "Conversation not found.")
        cid = conv["id"]
        cancel = runs.start(cid)
        try:
            history = repo.history_for_rag(cid)
            repo.update_conversation(user_id, cid, category=req.category, answer_mode=req.answer_mode)
            user_msg = repo.add_message(cid, "user", req.question)
        except Exception:
            runs.finish(cid)
            raise
        first = conv["message_count"] == 0
    elif req.save:
        conv = repo.create_conversation(user_id, category=req.category, answer_mode=req.answer_mode)
        cid = conv["id"]
        cancel = runs.start(cid)
        history = [t.model_dump() for t in req.history] if req.history else None
        user_msg = repo.add_message(cid, "user", req.question)
        first = True
    else:
        cid, user_msg, first, cancel = None, None, False, threading.Event()
        history = [t.model_dump() for t in req.history] if req.history else None

    return _job(user_id, endpoint, req.question, req.category, req.answer_mode, req.top_k, req.verify, history,
                cid, user_msg, first, req.followups, cancel)


def _prepare_rewind(user_id: str, message_id: str, body: RegenerateRequest, endpoint: str,
                    rewind: Callable[[], dict | None]) -> ChatJob:
    msg = repo.get_message(user_id, message_id)
    if not msg:
        raise APIError(404, "message_not_found", "Message not found.")
    cid = msg["conversation_id"]
    cancel = runs.start(cid)
    try:
        try:
            state = rewind()
        except ValueError as e:
            raise APIError(400, "invalid_message", str(e))
        if state is None:
            raise APIError(404, "message_not_found", "Message not found.")
        conv = state["conversation"]
        category = body.category or conv["category"]
        answer_mode = body.answer_mode or conv["answer_mode"]
        if body.category or body.answer_mode:
            repo.update_conversation(user_id, cid, category=category, answer_mode=answer_mode)
        return _job(user_id, endpoint, state["user_message"]["content"], category, answer_mode, body.top_k,
                    body.verify, state["history"], cid, state["user_message"], state["first_exchange"],
                    body.followups, cancel)
    except Exception:
        runs.finish(cid)
        raise


def prepare_regenerate(user_id: str, message_id: str, body: RegenerateRequest) -> ChatJob:
    return _prepare_rewind(user_id, message_id, body, "regenerate",
                           lambda: repo.rewind_for_regenerate(user_id, message_id))


def prepare_edit(user_id: str, message_id: str, body: EditRequest) -> ChatJob:
    return _prepare_rewind(user_id, message_id, body, "edit",
                           lambda: repo.rewind_for_edit(user_id, message_id, body.question))


def _release(job: ChatJob) -> None:
    if job.conversation_id:
        runs.finish(job.conversation_id)


# ── Extras, persistence, logging ─────────────────────────────────────────────

def _extras(job: ChatJob, mode: str, answer: str) -> dict:
    """Follow-up suggestions and (for a conversation's first exchange) an AI title."""
    want_title = job.want_title and job.conversation_id is not None
    if mode == "not_found":
        followups = [q for q in starter_questions(job.category, 4) if q != job.question][:3]
        result = {"followups": followups if job.want_followups and settings.enable_followups else [], "title": None}
    else:
        result = followup_llm.suggest(job.question, answer, want_followups=job.want_followups,
                                      want_title=want_title)
    title = None
    if result["title"] and want_title:
        title = repo.set_auto_title(job.conversation_id, result["title"], job.question)
    return {"followups": result["followups"], "title": title}


def _top_sources(sources: list[dict]) -> list[dict]:
    return [{"doc_id": s["doc_id"], "page": s["page_number"], "score": s["relevance_score"]} for s in sources[:3]]


def _persist(job: ChatJob, o: dict) -> str | None:
    """Saves the assistant message (saved chats) and the query log. Never raises."""
    message_id = None
    if job.conversation_id:
        try:
            msg = repo.add_message(
                job.conversation_id, "assistant", o["answer"],
                status=o["status"], mode=o["mode"],
                sources=o["sources"] if o["mode"] == "regulatory" else [],
                verification=o["verification"], confidence=o["confidence"], revised=o["revised"],
                standalone_question=o["standalone_question"], model=o["model"], latency_ms=o["latency_ms"],
                followups=o["followups"] or None,
            )
            message_id = msg["id"]
        except Exception as e:
            logger.warning(f"Saving assistant message failed: {e}")
    ver = o["verification"] or {}
    try:
        repo.log_query(
            request_id=job.request_id, user_id=job.user_id, conversation_id=job.conversation_id,
            message_id=message_id, endpoint=job.endpoint, question=job.question, category=job.category,
            answer_mode=job.answer_mode, standalone_question=o["standalone_question"], mode=o["mode"],
            grounded=o["grounded"], gate_score=o["gate_score"], top_sources=_top_sources(o["sources"]),
            verification_status=ver.get("status"), verification_score=ver.get("score"), revised=o["revised"],
            confidence=o["confidence"], model=o["model"], latency_ms=o["latency_ms"], timings=o["timings"],
            error=o["error"],
        )
    except Exception as e:
        logger.warning(f"Query log failed: {e}")
    return message_id


def _outcome(**overrides) -> dict:
    base = {"status": "complete", "answer": "", "mode": None, "sources": [], "verification": None,
            "confidence": None, "revised": False, "standalone_question": None, "model": None,
            "latency_ms": None, "followups": [], "grounded": None, "gate_score": None, "timings": None,
            "error": None}
    return {**base, **overrides}


# ── Non-streaming ────────────────────────────────────────────────────────────

def run_chat(job: ChatJob) -> dict:
    try:
        try:
            result = pipeline.answer(job.rag)
        except Exception as e:
            _persist(job, _outcome(status="error", error=type(e).__name__))
            raise
        extras = _extras(job, result.mode, result.answer)
        message_id = _persist(job, _outcome(
            answer=result.answer, mode=result.mode, sources=result.sources, verification=result.verification,
            confidence=result.confidence, revised=result.revised, standalone_question=result.standalone_question,
            model=result.model, latency_ms=result.latency_ms, followups=extras["followups"],
            grounded=result.grounded, gate_score=result.gate_score, timings=result.timings,
        ))
    finally:
        _release(job)

    return {
        "conversation_id": job.conversation_id,
        "message_id": message_id,
        "user_message_id": job.user_message["id"] if job.user_message else None,
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
        "followups": extras["followups"],
        "title": extras["title"],
    }


# ── Streaming ────────────────────────────────────────────────────────────────

def _execute(job: ChatJob, emit: Callable[[object], None]) -> None:
    """Worker thread: runs the pipeline, forwards events, persists, releases the slot."""
    t0 = time.perf_counter()
    text: list[str] = []
    st: dict = {"sources": [], "mode": None, "verification": None, "revised": False, "retrieval": {},
                "done": None, "error": None, "followups": []}
    try:
        for event in pipeline.stream(job.rag):
            if job.cancel.is_set():
                break
            etype = event["type"]
            if etype == "token":
                text.append(event["content"])
            elif etype == "retrieval":
                st["sources"], st["mode"], st["retrieval"] = event["sources"], event["mode"], event
            elif etype == "revision":
                text[:] = [event["answer"]]
                st["mode"] = event.get("mode", st["mode"])
                st["revised"] = st["revised"] or event.get("reason") == "repair"
                if "sources" in event:
                    st["sources"] = event["sources"]
            elif etype == "verification" and event.get("final"):
                st["verification"] = {k: v for k, v in event.items() if k not in ("type", "final")}
            elif etype == "done":
                st["done"] = event
                continue
            elif etype == "error":
                st["error"] = event
            emit(event)
            if etype == "error":
                break

        if st["done"] and not job.cancel.is_set():
            extras = _extras(job, st["done"]["mode"], st["done"].get("answer") or "".join(text))
            if extras["followups"]:
                st["followups"] = extras["followups"]
                emit({"type": "followups", "followups": extras["followups"]})
            if extras["title"]:
                emit({"type": "title", "conversation_id": job.conversation_id, "title": extras["title"]})
    except Exception as e:
        logger.exception(f"Chat job failed: {e}")
        st["error"] = {"type": "error", "code": "internal_error", "message": "Something went wrong while answering."}
        emit(st["error"])
    finally:
        done = st["done"] or {}
        if st["done"] and not st["error"]:
            status = "complete"
        elif job.cancel.is_set() and not st["error"]:
            status = "stopped"
        else:
            status = "error"
            if not st["error"]:
                st["error"] = {"type": "error", "code": "internal_error", "message": "The answer ended unexpectedly."}
                emit(st["error"])
        answer = (done.get("answer") or "".join(text)).strip()
        mode = done.get("mode") or st["mode"]
        latency_ms = done.get("latency_ms") or round((time.perf_counter() - t0) * 1000)
        retrieval = st["retrieval"]
        message_id = _persist(job, _outcome(
            status=status, answer=answer, mode=mode, sources=st["sources"], verification=st["verification"],
            confidence=done.get("confidence"), revised=st["revised"],
            standalone_question=retrieval.get("standalone_question"), model=done.get("model"),
            latency_ms=latency_ms, followups=st["followups"], grounded=retrieval.get("grounded"),
            gate_score=retrieval.get("gate_score"), timings=retrieval.get("timings"),
            error=(st["error"] or {}).get("code") if status == "error" else ("stopped" if status == "stopped" else None),
        ))
        _release(job)
        emit({
            "type": "done", "status": status, "message_id": message_id,
            "conversation_id": job.conversation_id, "mode": mode, "answer": answer,
            "confidence": done.get("confidence"), "model": done.get("model"), "latency_ms": latency_ms,
        })
        emit(_END)


def start_stream(job: ChatJob) -> AsyncIterator[str]:
    """Starts the worker immediately and returns the SSE relay. Call from the event loop."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(item: object) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # event loop closed (shutdown)
            pass

    threading.Thread(target=_execute, args=(job, emit), name="chat-job", daemon=True).start()
    return _relay(job, queue)


async def _relay(job: ChatJob, queue: asyncio.Queue) -> AsyncIterator[str]:
    finished = False
    try:
        if job.conversation_id:
            yield sse("conversation", {
                "conversation_id": job.conversation_id,
                "user_message_id": job.user_message["id"] if job.user_message else None,
            })
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=settings.sse_heartbeat_seconds)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is _END:
                finished = True
                return
            yield sse(item["type"], {k: v for k, v in item.items() if k != "type"})
    finally:
        if not finished:
            job.cancel.set()  # client went away: stop generating, the worker saves the partial answer


def stop(user_id: str, conversation_id: str) -> bool:
    if not repo.conversation_exists(user_id, conversation_id):
        raise APIError(404, "conversation_not_found", "Conversation not found.")
    return runs.cancel(conversation_id)
