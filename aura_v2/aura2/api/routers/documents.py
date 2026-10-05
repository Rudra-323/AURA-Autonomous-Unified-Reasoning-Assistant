from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from redis import Redis
from rq import Queue

from api.deps import get_current_user_id
from config.settings import get_settings
from ingestion import jobs
from ingestion.pipeline import new_document_id, new_job_id
from rag.embeddings import content_hash
from utils.errors import DatabaseError
from utils.logging import get_logger

router = APIRouter(prefix="/documents", tags=["documents"])
log = get_logger("api.documents")

_UPLOAD_DIR = Path("storage/uploads")


def _get_queue() -> Queue:
    settings = get_settings()
    return Queue("ingestion", connection=Redis.from_url(settings.redis_url))


@router.post("/upload")
async def upload_document(file: UploadFile, user_id: str = Depends(get_current_user_id)) -> dict:
    """Returns immediately with a job_id — parsing/chunking/embedding runs
    in a background worker, never inline in this request (see
    ingestion/pipeline.py's module docstring for why that matters)."""
    settings = get_settings()
    raw = await file.read()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb}MB limit.")

    file_hash = content_hash(raw)
    new_id = new_document_id()

    try:
        is_new, document_id = await jobs.create_document_record(
            new_id, user_id, file.filename, file.content_type or "", file_hash, len(raw)
        )
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=exc.user_message) from exc

    if not is_new:
        # Same file as before (by content), but "a documents row exists"
        # doesn't mean it actually finished — check the real job status
        # before deciding whether this is a no-op or a retry.
        latest_job = await jobs.get_latest_job_for_document(document_id, user_id)
        if latest_job and latest_job["status"] == "done":
            return {
                "status": "already_processed", "document_id": document_id,
                "message": "This file was already processed and is searchable.",
            }
        if latest_job and latest_job["status"] in ("pending", "processing"):
            # Already running — hand back its existing job_id rather than
            # starting a redundant second one.
            return {"status": "processing", "job_id": latest_job["job_id"], "document_id": document_id}
        # No job row at all, or status == "failed": the previous attempt
        # never completed (crashed, worker wasn't running, etc). Retry it —
        # which means actually saving the bytes again, since a failed/
        # missing attempt may never have had a usable file on disk.
        log.info("document.retrying_incomplete_upload", extra={"document_id": document_id, "user_id": user_id})

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _UPLOAD_DIR / f"{document_id}_{file.filename}"
    local_path.write_bytes(raw)

    job_id = new_job_id()
    await jobs.create_job(job_id, document_id, user_id)

    _get_queue().enqueue(
        "workers.ingestion_worker.run_ingestion_job",
        job_id, document_id, user_id, str(local_path), file.content_type or "", file.filename,
    )
    log.info("document.upload_enqueued", extra={"job_id": job_id, "user_id": user_id})
    return {"status": "processing", "job_id": job_id, "document_id": document_id}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    status = await jobs.get_job_status(job_id, user_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return status
