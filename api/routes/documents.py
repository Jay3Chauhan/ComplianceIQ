"""GET /api/documents — list all ingested documents. Also exposes /api/health."""

import time
from fastapi import APIRouter, HTTPException
from loguru import logger
from api.models import DocumentInfo, HealthResponse
from retrieval.retriever import get_all_documents
from ingestion.embedder import get_qdrant_client
from config import settings

router = APIRouter()

# Simple in-process cache — avoids a full Qdrant scroll on every sidebar load
_docs_cache: list[dict] = []
_docs_cache_ts: float = 0.0
_CACHE_TTL = 120  # seconds


def _get_documents_cached() -> list[dict]:
    global _docs_cache, _docs_cache_ts
    if time.time() - _docs_cache_ts < _CACHE_TTL and _docs_cache:
        return _docs_cache
    _docs_cache = get_all_documents()
    _docs_cache_ts = time.time()
    return _docs_cache


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents() -> list[DocumentInfo]:
    """Returns all unique documents currently in the vector store (cached 2 min)."""
    try:
        docs = _get_documents_cached()
        return [DocumentInfo(**d) for d in docs]
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    try:
        client = get_qdrant_client()
        collection_info = client.get_collection(settings.qdrant_collection)
        return HealthResponse(
            status="healthy",
            qdrant_connected=True,
            collection_name=settings.qdrant_collection,
            total_vectors=collection_info.points_count or 0,
            model=settings.groq_model,
        )
    except Exception as e:
        logger.warning(f"Health check degraded: {e}")
        return HealthResponse(
            status="degraded",
            qdrant_connected=False,
            collection_name=settings.qdrant_collection,
            total_vectors=0,
            model=settings.groq_model,
        )
