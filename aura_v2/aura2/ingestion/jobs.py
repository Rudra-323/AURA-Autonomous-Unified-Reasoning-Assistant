from __future__ import annotations

from database.connection import get_connection
from utils.errors import DatabaseError


async def create_document_record(document_id: str, user_id: str, filename: str,
                                  content_type: str, content_hash: str, size_bytes: int) -> tuple[bool, str]:
    """Returns (is_new, document_id). is_new=False means this exact file (by
    content hash) was already recorded for this user — document_id is then
    the EXISTING row's id, not the freshly generated one passed in, so the
    caller can check on that document's actual processing status rather
    than assuming "already recorded" means "already fully processed"."""
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                """INSERT INTO documents (document_id, user_id, filename, content_type, content_hash, size_bytes)
                   VALUES (%(id)s, %(user_id)s, %(filename)s, %(ct)s, %(hash)s, %(size)s)
                   ON CONFLICT (user_id, content_hash) DO NOTHING
                   RETURNING document_id""",
                {"id": document_id, "user_id": user_id, "filename": filename,
                 "ct": content_type, "hash": content_hash, "size": size_bytes},
            )
            row = await cur.fetchone()
            if row is not None:
                return True, row["document_id"]

            existing = await conn.execute(
                "SELECT document_id FROM documents WHERE user_id = %(user_id)s AND content_hash = %(hash)s",
                {"user_id": user_id, "hash": content_hash},
            )
            existing_row = await existing.fetchone()
            return False, existing_row["document_id"]
    except Exception as exc:  # noqa: BLE001
        raise DatabaseError(f"Failed to record document: {exc}") from exc


async def get_latest_job_for_document(document_id: str, user_id: str) -> dict | None:
    """Used when a re-upload matches an existing document, to check whether
    that document actually finished processing last time, or is stuck/
    failed and genuinely needs a retry — "a documents row exists" alone
    doesn't tell you which of those is true."""
    async with get_connection() as conn:
        cur = await conn.execute(
            """SELECT * FROM ingestion_jobs WHERE document_id = %(doc_id)s AND user_id = %(user_id)s
               ORDER BY created_at DESC LIMIT 1""",
            {"doc_id": document_id, "user_id": user_id},
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_job(job_id: str, document_id: str, user_id: str) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO ingestion_jobs (job_id, document_id, user_id) VALUES (%(job_id)s, %(doc_id)s, %(user_id)s)",
            {"job_id": job_id, "doc_id": document_id, "user_id": user_id},
        )


async def update_job(job_id: str, *, status: str | None = None, chunks_total: int | None = None,
                      chunks_done: int | None = None, error_message: str | None = None) -> None:
    fields, params = [], {"job_id": job_id}
    if status is not None:
        fields.append("status = %(status)s"); params["status"] = status
    if chunks_total is not None:
        fields.append("chunks_total = %(chunks_total)s"); params["chunks_total"] = chunks_total
    if chunks_done is not None:
        fields.append("chunks_done = %(chunks_done)s"); params["chunks_done"] = chunks_done
    if error_message is not None:
        fields.append("error_message = %(error_message)s"); params["error_message"] = error_message
    fields.append("updated_at = now()")
    async with get_connection() as conn:
        await conn.execute(f"UPDATE ingestion_jobs SET {', '.join(fields)} WHERE job_id = %(job_id)s", params)


async def get_job_status(job_id: str, user_id: str) -> dict | None:
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM ingestion_jobs WHERE job_id = %(job_id)s AND user_id = %(user_id)s",
            {"job_id": job_id, "user_id": user_id},
        )
        row = await cur.fetchone()
        return dict(row) if row else None
