"""
The actual answer to "user uploads a long PDF or multiple files — how is
that handled without blocking or high latency":

1. This function is NEVER called inline from an HTTP request handler — the
   API layer only enqueues it (see workers/ingestion_worker.py + api/routers
   for the upload endpoint) and returns a job_id immediately.
2. Chunks are embedded in BATCHES, not one at a time — the single biggest
   latency/cost lever for a large document.
3. Chunks are inserted into document_chunks as each batch completes, not
   after the whole document finishes — a huge document becomes partially
   queryable within seconds, not minutes.
4. Content-hash dedup means re-uploading the same file costs nothing.
"""

from __future__ import annotations

import uuid

from database.connection import get_connection
from ingestion import jobs
from ingestion.parsers import parse_document
from rag.chunking import chunk_text
from rag.embeddings import embed_passages
from utils.errors import IngestionError
from utils.logging import get_logger

log = get_logger("ingestion.pipeline")

_EMBED_BATCH_SIZE = 50


async def _insert_chunk_batch(user_id: str, document_id: str, start_index: int,
                               texts: list[str], embeddings: list[list[float]]) -> None:
    async with get_connection() as conn:
        for offset, (text, emb) in enumerate(zip(texts, embeddings)):
            await conn.execute(
                """INSERT INTO document_chunks (document_id, user_id, chunk_index, content, embedding)
                   VALUES (%(doc_id)s, %(user_id)s, %(idx)s, %(content)s, %(emb)s)""",
                {"doc_id": document_id, "user_id": user_id, "idx": start_index + offset,
                 "content": text, "emb": str(emb)},
            )


async def ingest_document(job_id: str, document_id: str, user_id: str,
                           local_path: str, content_type: str, filename: str) -> None:
    """The full pipeline for one document. Runs in a background worker, not
    the request path. Updates ingestion_jobs throughout so the UI can poll
    or subscribe to progress."""
    try:
        await jobs.update_job(job_id, status="processing")

        text = parse_document(local_path, content_type, filename)
        chunks = chunk_text(text)
        await jobs.update_job(job_id, chunks_total=len(chunks))

        done = 0
        for i in range(0, len(chunks), _EMBED_BATCH_SIZE):
            batch = chunks[i:i + _EMBED_BATCH_SIZE]
            embeddings = await embed_passages(batch)
            await _insert_chunk_batch(user_id, document_id, i, batch, embeddings)
            done += len(batch)
            await jobs.update_job(job_id, chunks_done=done)
            log.info("ingestion.progress", extra={"job_id": job_id, "done": done, "total": len(chunks)})

        await jobs.update_job(job_id, status="done")
        log.info("ingestion.complete", extra={"job_id": job_id, "document_id": document_id})

    except IngestionError as exc:
        await jobs.update_job(job_id, status="failed", error_message=exc.user_message)
        log.warning("ingestion.failed", extra={"job_id": job_id, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001 — always record failure, never leave a job stuck "processing"
        await jobs.update_job(job_id, status="failed", error_message="Unexpected error during processing.")
        log.error("ingestion.unexpected_error", extra={"job_id": job_id, "error": str(exc)})


def new_document_id() -> str:
    return str(uuid.uuid4())


def new_job_id() -> str:
    return str(uuid.uuid4())
