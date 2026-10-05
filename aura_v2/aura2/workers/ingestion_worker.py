"""
RQ (Redis Queue) worker function. RQ workers call plain sync functions, so
this is a thin asyncio.run() wrapper around the real async pipeline — the
pipeline itself stays async/testable independent of the queue technology.

Enqueue from the API layer with:
    from redis import Redis
    from rq import Queue
    queue = Queue("ingestion", connection=Redis.from_url(settings.redis_url))
    queue.enqueue(run_ingestion_job, job_id, document_id, user_id, local_path, content_type, filename)

Run the worker process with:
    rq worker ingestion --url redis://localhost:6379/0
"""

from __future__ import annotations

import asyncio

from ingestion.pipeline import ingest_document
from utils.asyncio_compat import fix_windows_event_loop
from utils.logging import get_logger

fix_windows_event_loop()  # must run before asyncio.run() below — separate
# process from api/main.py, so it needs its own call, not inherited from it

log = get_logger("workers.ingestion")


def run_ingestion_job(job_id: str, document_id: str, user_id: str,
                       local_path: str, content_type: str, filename: str) -> None:
    log.info("worker.ingestion_started", extra={"job_id": job_id})
    asyncio.run(ingest_document(job_id, document_id, user_id, local_path, content_type, filename))
