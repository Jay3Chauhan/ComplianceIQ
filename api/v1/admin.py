"""Admin endpoints (X-Admin-Key): document upload/reindex/delete, jobs, stats."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from api.errors import APIError
from api.schemas import DeleteResult, DocumentMetadataUpdate, IngestJob
from api.security import require_admin
from api.services import jobs
from config import settings
from db import repository as repo
from ingestion.embedder import delete_by_filename
from ingestion.registry import (
    DOCS_DIR,
    doc_id_for,
    get_entry,
    pdf_path_for,
    remove_entry,
    safe_filename,
    upsert_entry,
)
from retrieval import catalog
from retrieval.cache import clear_all_caches

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

CATEGORY_PATTERN = "^(RBI|SEBI|AA|GENERAL)$"


async def _save_upload(upload: UploadFile, dest: Path) -> int:
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    tmp = dest.with_suffix(".uploading")
    try:
        with tmp.open("wb") as fh:
            first = True
            while chunk := await upload.read(1024 * 1024):
                if first and not chunk.startswith(b"%PDF"):
                    raise APIError(415, "invalid_file", "Only PDF files are accepted.")
                first = False
                size += len(chunk)
                if size > limit:
                    raise APIError(413, "file_too_large", f"PDF exceeds {settings.max_upload_mb} MB.")
                fh.write(chunk)
        if size == 0:
            raise APIError(400, "empty_file", "Uploaded file is empty.")
        tmp.replace(dest)
        return size
    finally:
        tmp.unlink(missing_ok=True)


@router.post("/documents", status_code=202)
async def upload_document(
    file: UploadFile = File(..., description="PDF file"),
    name: str = Form(..., min_length=3, max_length=200),
    category: str = Form(..., pattern=CATEGORY_PATTERN),
    circular_id: str = Form("", max_length=120),
    subcategory: str = Form("", max_length=120),
    date: str = Form("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"),
    issuer: str = Form("", max_length=200),
    url: str = Form("", max_length=500),
    replace: bool = Form(False, description="Overwrite an existing document with the same filename"),
) -> dict:
    """Uploads a PDF, registers its metadata and queues ingestion. Poll the returned job."""
    filename = safe_filename(file.filename or name)
    existing = get_entry(filename)
    if existing and not replace:
        raise APIError(409, "document_exists", f"'{filename}' already exists. Set replace=true to overwrite.")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    size = await _save_upload(file, DOCS_DIR / filename)
    meta = upsert_entry({
        "filename": filename, "name": name, "circular_id": circular_id, "category": category,
        "subcategory": subcategory, "date": date, "issuer": issuer, "url": url,
    })
    job = await asyncio.to_thread(jobs.enqueue, meta["doc_id"], filename)
    clear_all_caches()
    return {"document": {**meta, "size_bytes": size}, "job": job}


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: str, body: DocumentMetadataUpdate) -> dict:
    """Updates registry metadata and re-indexes so citations reflect the change."""
    entry = get_entry(doc_id)
    if not entry:
        raise APIError(404, "document_not_found", "Document not found.")
    meta = upsert_entry({**entry, **body.model_dump(exclude_none=True)})
    job = await asyncio.to_thread(jobs.enqueue, meta["doc_id"], meta["filename"]) if pdf_path_for(meta).exists() else None
    clear_all_caches()
    return {"document": meta, "job": job}


@router.post("/documents/{doc_id}/reindex", response_model=IngestJob, status_code=202)
async def reindex_document(doc_id: str) -> dict:
    entry = get_entry(doc_id)
    if not entry:
        raise APIError(404, "document_not_found", "Document not found.")
    if not pdf_path_for(entry).exists():
        raise APIError(404, "file_not_found", "PDF file is missing on the server.")
    return await asyncio.to_thread(jobs.enqueue, entry["doc_id"], entry["filename"])


@router.post("/reindex", status_code=202)
async def reindex_all() -> dict:
    """Queues re-ingestion of every registered document that has a PDF."""
    queued = []
    for doc in await asyncio.to_thread(catalog.list_documents, None, False):
        if doc["has_file"]:
            queued.append(await asyncio.to_thread(jobs.enqueue, doc["doc_id"], doc["filename"]))
    return {"jobs": queued}


@router.delete("/documents/{doc_id}", response_model=DeleteResult)
async def delete_document(doc_id: str, delete_file: bool = Query(False)) -> dict:
    entry = get_entry(doc_id)
    if not entry:
        raise APIError(404, "document_not_found", "Document not found.")
    if repo.active_job_for(entry["doc_id"]):
        raise APIError(409, "job_running", "An ingestion job is running for this document.")
    await asyncio.to_thread(delete_by_filename, entry["filename"])
    remove_entry(entry["filename"])
    file_deleted = False
    if delete_file and pdf_path_for(entry).exists():
        pdf_path_for(entry).unlink()
        file_deleted = True
    clear_all_caches()
    return {"deleted": True, "doc_id": doc_id_for(entry["filename"]), "file_deleted": file_deleted}


@router.get("/jobs", response_model=list[IngestJob])
async def list_jobs(limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    return await asyncio.to_thread(repo.list_jobs, limit)


@router.get("/jobs/{job_id}", response_model=IngestJob)
async def get_job(job_id: str) -> dict:
    job = await asyncio.to_thread(repo.get_job, job_id)
    if not job:
        raise APIError(404, "job_not_found", "Job not found.")
    return job


@router.get("/stats")
async def stats(days: int = Query(7, ge=1, le=90)) -> dict:
    """Usage analytics, index statistics and document coverage."""
    usage = await asyncio.to_thread(repo.usage_stats, days)
    try:
        index = await asyncio.to_thread(catalog.collection_stats)
    except Exception as e:
        index = {"error": str(e)[:200]}
    docs = await asyncio.to_thread(catalog.list_documents, None, False)
    return {
        "usage": usage,
        "index": index,
        "documents": {
            "total": len(docs),
            "indexed": sum(d["indexed"] for d in docs),
            "by_category": {c: sum(1 for d in docs if d["category"] == c) for c in sorted({d["category"] for d in docs})},
        },
    }


@router.post("/cache/clear", status_code=204)
async def clear_cache() -> None:
    clear_all_caches()
