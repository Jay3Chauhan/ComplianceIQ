"""
FastAPI application entry point.
Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from api.routes import query, ingest, documents
from config import settings


async def _warmup() -> None:
    """Eagerly initialise heavy singletons off the event loop."""
    t0 = time.perf_counter()
    logger.info("Warming up embedding model…")
    from ingestion.embedder import get_embedding_model, get_qdrant_client

    await asyncio.to_thread(get_embedding_model)
    logger.info(f"Embedding model ready ({time.perf_counter() - t0:.1f}s)")

    t1 = time.perf_counter()
    await asyncio.to_thread(get_qdrant_client)
    logger.info(f"Qdrant connected ({time.perf_counter() - t1:.1f}s)")

    if settings.enable_rerank:
        t2 = time.perf_counter()
        try:
            from retrieval.reranker import get_reranker

            await asyncio.to_thread(get_reranker, settings.reranker_model)
            logger.info(f"Reranker ready ({time.perf_counter() - t2:.1f}s)")
        except Exception as e:
            logger.warning(f"Reranker warmup skipped: {e}")

    logger.info(f"All systems ready — warmup {time.perf_counter() - t0:.1f}s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("COMPLIANCEIQ_SKIP_WARMUP") == "1":
        logger.info("Skipping warmup (COMPLIANCEIQ_SKIP_WARMUP=1)")
    else:
        await _warmup()
    logger.info("Docs available at http://localhost:8000/docs")
    yield
    logger.info("ComplianceIQ API shutting down.")


app = FastAPI(
    title="ComplianceIQ API",
    description="Production RAG Q&A for RBI/SEBI/AA Indian regulatory documents",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, prefix="/api", tags=["Query"])
app.include_router(ingest.router, prefix="/api", tags=["Ingestion"])
app.include_router(documents.router, prefix="/api", tags=["Documents"])


@app.get("/")
async def root() -> dict:
    return {
        "name": "ComplianceIQ",
        "version": "1.1.0",
        "description": "RBI/SEBI Regulatory RAG Bot",
        "docs": "/docs",
        "health": "/api/health",
    }
