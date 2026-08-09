"""POST /api/query — standard and streaming RAG endpoints."""

import json
import time
import asyncio
from collections.abc import Iterator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from api.models import QueryRequest, QueryResponse
from retrieval.retriever import retrieve_chunks
from llm.groq_client import (
    generate_answer,
    generate_answer_stream,
    not_found_response,
    _build_sources,
)

router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _resolve_mode(
    req: QueryRequest,
    chunks: list[dict],
    is_grounded: bool,
) -> tuple[list[dict], bool, str]:
    """Returns (chunks_for_llm, is_grounded_for_llm, mode_label)."""
    answer_mode = req.answer_mode or "auto"

    if answer_mode == "general":
        return [], False, "general"

    if answer_mode == "regulatory":
        if is_grounded and chunks:
            return chunks, True, "regulatory"
        return [], False, "not_found"

    if is_grounded and chunks:
        return chunks, True, "regulatory"
    return [], False, "general"


def _run_rag(req: QueryRequest) -> dict:
    t0 = time.perf_counter()

    if (req.answer_mode or "auto") == "general":
        chunks, is_grounded = [], False
    else:
        chunks, is_grounded = retrieve_chunks(
            query=req.question,
            top_k=req.top_k,
            category_filter=req.category,
        )

    chunks, grounded, mode = _resolve_mode(req, chunks, is_grounded)

    if mode == "not_found":
        result = not_found_response()
    else:
        result = generate_answer(
            question=req.question,
            chunks=chunks,
            history=req.history,
            is_grounded=grounded,
        )
        result["mode"] = mode

    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return result


@router.post("/query", response_model=QueryResponse)
async def query_regulations(req: QueryRequest) -> QueryResponse:
    """Standard (non-streaming) RAG endpoint."""
    logger.info(
        f"Query: '{req.question[:80]}...' | category={req.category} | mode={req.answer_mode}"
    )
    try:
        result = await asyncio.to_thread(_run_rag, req)
        return QueryResponse(**result)
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail="Query failed. Check server logs.")


def _sse_stream(req: QueryRequest) -> Iterator[str]:
    t0 = time.perf_counter()
    yield _sse({"type": "status", "stage": "searching", "message": "Searching regulatory documents…"})

    try:
        if (req.answer_mode or "auto") == "general":
            chunks, is_grounded = [], False
        else:
            chunks, is_grounded = retrieve_chunks(
                query=req.question,
                top_k=req.top_k,
                category_filter=req.category,
            )
        chunks, grounded, mode = _resolve_mode(req, chunks, is_grounded)
    except Exception as e:
        yield _sse({"type": "error", "content": "Retrieval failed. Please try again."})
        logger.error(f"Stream retrieve failed: {e}")
        return

    sources = _build_sources(chunks) if grounded else []
    yield _sse({"type": "meta", "sources": sources, "mode": mode})

    if mode == "not_found":
        from llm.prompt_templates import NOT_FOUND_ANSWER

        yield _sse({"type": "status", "stage": "done", "message": "No grounded match"})
        yield _sse({"type": "token", "content": NOT_FOUND_ANSWER})
        yield _sse({
            "type": "usage",
            "usage": {},
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        })
        yield "data: [DONE]\n\n"
        return

    if mode == "regulatory":
        yield _sse({
            "type": "status",
            "stage": "thinking",
            "message": f"Found {len(sources)} sources — drafting cited answer…",
        })
    else:
        yield _sse({
            "type": "status",
            "stage": "thinking",
            "message": "No strong circular match — answering with general finance knowledge…",
        })

    yield _sse({"type": "status", "stage": "writing", "message": "Writing answer…"})

    try:
        for event in generate_answer_stream(
            question=req.question,
            chunks=chunks,
            history=req.history,
            is_grounded=grounded,
        ):
            if event["type"] == "token":
                yield _sse({"type": "token", "content": event["content"]})
            elif event["type"] == "error":
                yield _sse({"type": "error", "content": event["content"]})
                return
    except Exception as e:
        logger.error(f"Stream generation failed: {e}")
        yield _sse({"type": "error", "content": "Answer generation failed. Please try again."})
        return

    yield _sse({
        "type": "usage",
        "usage": {},
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    })
    yield _sse({"type": "status", "stage": "done", "message": "Done"})
    yield "data: [DONE]\n\n"


@router.post("/query/stream")
async def query_stream(req: QueryRequest) -> StreamingResponse:
    """Streaming RAG endpoint — status → sources → tokens."""
    logger.info(
        f"Stream: '{req.question[:80]}...' | category={req.category} | mode={req.answer_mode}"
    )
    return StreamingResponse(
        _sse_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
