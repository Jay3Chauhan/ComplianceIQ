"""Liveness (/health) and readiness (/ready) probes — no API key required."""

import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.v1.meta import APP_VERSION
from config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    """Process is up. Cheap; safe for frequent load-balancer checks."""
    return {"status": "ok", "version": APP_VERSION}


def _timed(fn) -> dict:
    t0 = time.perf_counter()
    try:
        detail = fn()
        return {"ok": True, "detail": detail, "latency_ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200], "latency_ms": round((time.perf_counter() - t0) * 1000)}


def _check_qdrant() -> str:
    from ingestion.embedder import get_qdrant_client

    info = get_qdrant_client().get_collection(settings.qdrant_collection)
    if not info.points_count:
        raise RuntimeError(f"collection '{settings.qdrant_collection}' is empty")
    return f"{settings.qdrant_collection}: {info.points_count} vectors"


def _check_db() -> str:
    from db.session import get_engine

    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return get_engine().dialect.name


def _check_models() -> str:
    from ingestion import embedder
    from retrieval import reranker

    loaded = {"dense": embedder._dense is not None, "sparse": embedder._sparse is not None}
    if settings.enable_rerank:
        loaded["reranker"] = reranker._cross_encoder is not None
    missing = [k for k, v in loaded.items() if not v]
    if missing:
        raise RuntimeError(f"not loaded: {', '.join(missing)}")
    return "all loaded"


@router.get("/ready")
async def ready() -> JSONResponse:
    """Dependencies are reachable and models are warm. 503 when degraded."""
    checks = {
        "qdrant": await asyncio.to_thread(_timed, _check_qdrant),
        "database": await asyncio.to_thread(_timed, _check_db),
        "models": _timed(_check_models),
        "llm": {"ok": bool(settings.groq_api_key), "detail": "configured" if settings.groq_api_key else "missing key"},
    }
    ok = all(c["ok"] for c in checks.values())
    return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)
