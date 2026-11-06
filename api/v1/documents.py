"""Document catalog, page passages, section outline and PDF download."""

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from api.errors import APIError
from api.schemas import DocumentOutline, DocumentPage, DocumentSummary
from retrieval import catalog
from ingestion.registry import get_entry, pdf_path_for

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("", response_model=list[DocumentSummary])
async def list_documents(category: str | None = Query(None, pattern="^(ALL|RBI|SEBI|AA|GENERAL)$")) -> list[dict]:
    return await asyncio.to_thread(catalog.list_documents, category)


@router.get("/{doc_id}", response_model=DocumentSummary)
async def get_document(doc_id: str) -> dict:
    doc = await asyncio.to_thread(catalog.get_document, doc_id)
    if not doc:
        raise APIError(404, "document_not_found", "Document not found.")
    return doc


@router.get("/{doc_id}/outline", response_model=DocumentOutline)
async def get_outline(doc_id: str) -> dict:
    outline = await asyncio.to_thread(catalog.get_outline, doc_id)
    if not outline:
        raise APIError(404, "document_not_found", "Document not found.")
    return outline


@router.get("/{doc_id}/pages/{page_number}", response_model=DocumentPage)
async def get_page(doc_id: str, page_number: int) -> dict:
    if page_number < 1:
        raise APIError(400, "invalid_page", "page_number starts at 1.")
    page = await asyncio.to_thread(catalog.get_page, doc_id, page_number)
    if not page:
        raise APIError(404, "document_not_found", "Document not found.")
    return page


@router.get("/{doc_id}/file", response_class=FileResponse)
async def download_file(doc_id: str) -> FileResponse:
    """Streams the original PDF (use `#page=N` in the viewer URL to jump to a citation)."""
    entry = get_entry(doc_id)
    if not entry:
        raise APIError(404, "document_not_found", "Document not found.")
    path = pdf_path_for(entry)
    if not path.exists():
        raise APIError(404, "file_not_found", "The PDF file is not available on this server.")
    return FileResponse(path, media_type="application/pdf", filename=entry["filename"],
                        content_disposition_type="inline")
