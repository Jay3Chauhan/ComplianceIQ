"""Legacy GET /api/documents and /api/health."""

import asyncio

from fastapi import APIRouter
from loguru import logger

from api.errors import APIError
from api.models import DocumentInfo, HealthResponse
from config import settings
from retrieval import catalog

router = APIRouter()


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents() -> list[DocumentInfo]:
    """Indexed documents (cached 2 min)."""
    try:
        docs = await asyncio.to_thread(catalog.list_documents)
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise APIError(503, "index_unavailable", "Could not reach the vector index.")
    return [
        DocumentInfo(
            doc_name=d["name"], circular_id=d["circular_id"], category=d["category"],
            date=d["date"], issuer=d["issuer"], source_url=d["source_url"],
        )
        for d in docs if d["indexed"]
    ]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    try:
        stats = await asyncio.to_thread(catalog.collection_stats)
        return HealthResponse(
            status="healthy", qdrant_connected=True, collection_name=settings.qdrant_collection,
            total_vectors=stats["points"], model=settings.groq_model, rerank_enabled=settings.enable_rerank,
        )
    except Exception as e:
        logger.warning(f"Health check degraded: {e}")
        return HealthResponse(
            status="degraded", qdrant_connected=False, collection_name=settings.qdrant_collection,
            total_vectors=0, model=settings.groq_model, rerank_enabled=settings.enable_rerank,
        )
