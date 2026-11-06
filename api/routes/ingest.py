"""Legacy POST /api/ingest (synchronous). New clients: /api/v1/admin/documents."""

import asyncio

from fastapi import APIRouter, Depends

from api.errors import APIError
from api.models import IngestRequest, IngestResponse
from api.security import require_admin
from ingestion.pipeline import ingest_document
from ingestion.registry import get_entry

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(require_admin)])
async def ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a registered PDF from data/documents/ (idempotent). Requires X-Admin-Key."""
    entry = get_entry(req.filename)
    if not entry:
        raise APIError(404, "document_not_found", f"'{req.filename}' is not in the document registry.")
    result = await asyncio.to_thread(ingest_document, entry)
    if result["status"] != "success":
        raise APIError(404, "file_not_found", f"PDF file not found for '{req.filename}'.")
    return IngestResponse(**{k: result[k] for k in ("status", "doc_name", "pages", "chunks", "vectors_stored")})
