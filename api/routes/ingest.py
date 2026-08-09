"""POST /api/ingest — admin endpoint to ingest documents."""

import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header
from loguru import logger
from api.models import IngestRequest, IngestResponse
from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks
from ingestion.embedder import embed_and_store
from config import settings

router = APIRouter()

REGISTRY_PATH = "data/document_registry.json"
DOCS_DIR = "data/documents"


def _require_admin(x_admin_key: str | None) -> None:
    if not settings.admin_api_key:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=503,
                detail="Ingest disabled: set ADMIN_API_KEY in production.",
            )
        return
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key header.")


def _ingest_sync(filename: str) -> IngestResponse:
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    doc_meta = next((d for d in registry if d["filename"] == filename), None)
    if not doc_meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{filename}' not found in registry.",
        )

    pdf_path = Path(DOCS_DIR) / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF file not found at {pdf_path}")

    pages = parse_pdf(str(pdf_path), doc_meta)
    chunks = create_chunks(pages)
    stored = embed_and_store(chunks, replace_existing=True)
    return IngestResponse(
        status="success",
        doc_name=doc_meta["name"],
        pages=len(pages),
        chunks=len(chunks),
        vectors_stored=stored,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    req: IngestRequest,
    x_admin_key: str | None = Header(default=None),
) -> IngestResponse:
    """
    Ingest a PDF into the vector store (idempotent by filename).
    Requires X-Admin-Key when ADMIN_API_KEY is configured.
    """
    _require_admin(x_admin_key)
    try:
        return await asyncio.to_thread(_ingest_sync, req.filename)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail="Ingestion failed. Check server logs.")
