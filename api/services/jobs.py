"""
Background ingestion jobs. A single worker thread keeps CPU-heavy embedding
from starving request handling; job state lives in the database so the
frontend can poll it.
"""

from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from db import repository as repo
from db.models import utcnow
from ingestion.pipeline import ingest_document
from ingestion.registry import get_entry

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")


def _run(job_id: str, doc_id: str) -> None:
    entry = get_entry(doc_id)
    if not entry:
        repo.update_job(job_id, status="failed", error="Document not in registry", finished_at=utcnow())
        return
    repo.update_job(job_id, status="running", stage="parsing", started_at=utcnow())

    def progress(stage: str, pct: float) -> None:
        repo.update_job(job_id, stage=stage, progress=pct)

    try:
        result = ingest_document(entry, progress=progress)
        status = "succeeded" if result.get("status") == "success" else "failed"
        repo.update_job(job_id, status=status, stage="done", progress=1.0, result=result,
                        error=result.get("reason"), finished_at=utcnow())
    except Exception as e:
        logger.exception(f"Ingest job {job_id} failed: {e}")
        repo.update_job(job_id, status="failed", error=str(e)[:1000], finished_at=utcnow())


def enqueue(doc_id: str, filename: str) -> dict:
    existing = repo.active_job_for(doc_id)
    if existing:
        return existing
    job = repo.create_job(doc_id, filename)
    _executor.submit(_run, job["id"], doc_id)
    return job


def fail_orphaned_jobs() -> None:
    """Jobs left queued/running by a previous process will never finish."""
    for job in repo.list_jobs(limit=100):
        if job["status"] in ("queued", "running"):
            repo.update_job(job["id"], status="failed", error="Interrupted by server restart", finished_at=utcnow())
