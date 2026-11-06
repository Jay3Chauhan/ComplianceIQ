"""
Legacy POST /api/query and /api/query/stream (kept for the Streamlit UI).
Runs on the v2 pipeline; new clients should use /api/v1/chat.
"""

import asyncio
import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from api.errors import APIError
from api.models import QueryRequest, QueryResponse
from api.security import rate_limit_chat
from llm.groq_client import LLMUnavailableError
from rag import pipeline
from rag.pipeline import RAGRequest

router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _rag_request(req: QueryRequest) -> RAGRequest:
    return RAGRequest(
        question=req.question,
        category=req.category or "ALL",
        top_k=req.top_k,
        answer_mode=req.answer_mode or "auto",
        history=req.history,
    )


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(rate_limit_chat)])
async def query_regulations(req: QueryRequest) -> QueryResponse:
    """Non-streaming RAG answer with citations and verification."""
    try:
        result = await asyncio.to_thread(pipeline.answer, _rag_request(req))
    except LLMUnavailableError:
        raise APIError(503, "llm_unavailable", "The language model is rate limited. Try again in a minute.")
    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        chunks_used=len(result.sources),
        usage=result.usage,
        mode=result.mode,
        latency_ms=result.latency_ms,
        confidence=result.confidence,
        verification=result.verification,
        revised=result.revised,
    )


def _legacy_stream(req: QueryRequest) -> Iterator[str]:
    for event in pipeline.stream(_rag_request(req)):
        etype = event["type"]
        if etype == "retrieval":
            yield _sse({"type": "meta", "sources": event["sources"], "mode": event["mode"]})
        elif etype == "error":
            yield _sse({"type": "error", "content": event["message"]})
            return
        elif etype == "done":
            yield _sse({"type": "usage", "usage": {}, "latency_ms": event["latency_ms"],
                        "confidence": event.get("confidence")})
            yield _sse({"type": "status", "stage": "done", "message": "Done"})
            yield "data: [DONE]\n\n"
            return
        else:
            yield _sse(event)


@router.post("/query/stream", dependencies=[Depends(rate_limit_chat)])
async def query_stream(req: QueryRequest) -> StreamingResponse:
    """Streaming RAG: status → meta (sources) → tokens → verification → [DONE]."""
    logger.info(f"Legacy stream | category={req.category} | mode={req.answer_mode}")
    return StreamingResponse(
        _legacy_stream(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
