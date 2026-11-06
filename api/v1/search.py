"""Passage search without generation (for a 'search the circulars' UI)."""

import asyncio

from fastapi import APIRouter, Depends

from api.schemas import SearchRequest, SearchResponse
from api.security import rate_limit_chat
from rag.pipeline import build_sources
from retrieval.retriever import retrieve

router = APIRouter(tags=["Search"])


@router.post("/search", response_model=SearchResponse, dependencies=[Depends(rate_limit_chat)])
async def search(req: SearchRequest) -> dict:
    """Hybrid search + rerank. Returns ranked passages even when weakly relevant."""
    result = await asyncio.to_thread(
        retrieve, req.query, top_k=req.top_k, category=req.category, rerank=req.rerank, apply_gate=False
    )
    return {
        "query": req.query,
        "search_query": result.search_query,
        "grounded": result.is_grounded,
        "gate_score": result.gate_score,
        "results": build_sources(result.chunks),
        "timings": result.timings,
    }
