"""POST /api/ingest — admin endpoint to ingest documents."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from loguru import logger
from api.models import IngestRequest, IngestResponse
from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks
from ingestion.embedder import embed_and_store

router = APIRouter()

REGISTRY_PATH = "data/document_registry.json"
DOCS_DIR = "data/documents"


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(req: IngestRequest) -> IngestResponse:
    """
    Ingest a PDF document into the vector store.
    The PDF must be present in data/documents/ and registered in document_registry.json.
    """
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    doc_meta = next((d for d in registry if d["filename"] == req.filename), None)

    if not doc_meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{req.filename}' not found in registry. Add it to document_registry.json first.",
        )

    pdf_path = Path(DOCS_DIR) / req.filename
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found at {pdf_path}",
        )

    try:
        pages = parse_pdf(str(pdf_path), doc_meta)
        chunks = create_chunks(pages)
        stored = embed_and_store(chunks)

        return IngestResponse(
            status="success",
            doc_name=doc_meta["name"],
            pages=len(pages),
            chunks=len(chunks),
            vectors_stored=stored,
        )
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
