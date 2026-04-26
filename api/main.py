"""
FastAPI application entry point.
Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from api.routes import query, ingest, documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ComplianceIQ API starting up...")
    logger.info("Docs available at http://localhost:8000/docs")
    yield
    logger.info("ComplianceIQ API shutting down.")


app = FastAPI(
    title="ComplianceIQ API",
    description="RAG-powered Q&A for RBI/SEBI Indian regulatory documents",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "description": "RBI/SEBI Regulatory RAG Bot",
        "docs": "/docs",
        "health": "/api/health",
    }
