"""
FastAPI application entry point.
Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api import v1
from api.errors import register_error_handlers
from api.middleware import RequestContextMiddleware
from api.routes import documents, ingest, query
from api.security import require_api_key
from api.v1.meta import APP_VERSION
from config import settings


async def _warmup() -> None:
    """Loads models and opens connections before the first request."""
    t0 = time.perf_counter()
    from ingestion.embedder import get_dense_model, get_qdrant_client, get_sparse_model

    await asyncio.to_thread(get_dense_model)
    await asyncio.to_thread(get_sparse_model)
    await asyncio.to_thread(get_qdrant_client)
    if settings.enable_rerank:
        from retrieval.reranker import get_reranker

        await asyncio.to_thread(get_reranker)
    logger.info(f"Models warm in {time.perf_counter() - t0:.1f}s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.services.jobs import fail_orphaned_jobs
    from db.session import init_db

    init_db()
    fail_orphaned_jobs()
    if settings.is_production and not settings.api_key_list:
        logger.error("API_KEYS is not set: protected endpoints will return 503 in production.")
    if os.getenv("COMPLIANCEIQ_SKIP_WARMUP") == "1":
        logger.info("Skipping warmup (COMPLIANCEIQ_SKIP_WARMUP=1)")
    else:
        await _warmup()
    logger.info("ComplianceIQ API ready — docs at /docs")
    yield
    logger.info("ComplianceIQ API shutting down.")


app = FastAPI(
    title="ComplianceIQ API",
    description=(
        "Grounded, cited Q&A over RBI / SEBI / Account Aggregator regulations.\n\n"
        "Use `/api/v1/*` for new integrations. `/api/query*` endpoints are kept for the Streamlit UI."
    ),
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-ms", "Retry-After"],
)
app.add_middleware(RequestContextMiddleware)
register_error_handlers(app)

app.include_router(v1.router)

legacy = [Depends(require_api_key)]
app.include_router(query.router, prefix="/api", tags=["Legacy"], dependencies=legacy)
app.include_router(ingest.router, prefix="/api", tags=["Legacy"], dependencies=legacy)
app.include_router(documents.router, prefix="/api", tags=["Legacy"])


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "name": "ComplianceIQ",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
        "ready": "/api/v1/ready",
    }
