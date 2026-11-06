"""
Single ingestion entry point shared by the CLI, the admin API and background jobs.
"""

import time
from collections.abc import Callable

from loguru import logger

from ingestion.chunker import create_chunks
from ingestion.embedder import embed_and_store
from ingestion.pdf_parser import parse_pdf
from ingestion.registry import pdf_path_for

ProgressCallback = Callable[[str, float], None]


def ingest_document(meta: dict, progress: ProgressCallback | None = None) -> dict:
    """
    Parses, chunks, embeds and stores one registered document.
    Re-ingesting replaces the document's previous vectors.
    """
    report = progress or (lambda stage, pct: None)
    pdf_path = pdf_path_for(meta)
    if not pdf_path.exists():
        logger.warning(f"PDF not found, skipping: {pdf_path}")
        return {"status": "skipped", "doc_id": meta.get("doc_id"), "doc_name": meta["name"],
                "reason": "file not found"}

    t0 = time.perf_counter()
    report("parsing", 0.05)
    pages = parse_pdf(str(pdf_path), meta)
    report("chunking", 0.2)
    chunks = create_chunks(pages)
    if not chunks:
        # Keep the document's previous vectors rather than replacing them with nothing.
        logger.warning(f"No extractable text in {pdf_path.name}; previous vectors kept")
        return {"status": "failed", "doc_id": meta.get("doc_id"), "doc_name": meta["name"],
                "filename": meta["filename"], "pages": len(pages), "chunks": 0, "vectors_stored": 0,
                "reason": "No extractable text: the PDF may be scanned or image-only (OCR is not supported)."}
    report("embedding", 0.3)
    stored = embed_and_store(chunks, show_progress=progress is None)
    report("done", 1.0)

    _invalidate_caches()
    return {
        "status": "success",
        "doc_id": meta.get("doc_id"),
        "doc_name": meta["name"],
        "filename": meta["filename"],
        "pages": len(pages),
        "chunks": len(chunks),
        "vectors_stored": stored,
        "duration_s": round(time.perf_counter() - t0, 1),
    }


def _invalidate_caches() -> None:
    try:
        from retrieval.cache import clear_all_caches

        clear_all_caches()
    except Exception as e:  # cache module optional during CLI runs
        logger.debug(f"Cache invalidation skipped: {e}")
