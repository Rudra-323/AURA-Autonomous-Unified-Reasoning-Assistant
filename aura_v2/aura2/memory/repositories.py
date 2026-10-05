"""
Long-term memory, async. v2 upgrade over v1: `recall_semantic` does
embedding-similarity search instead of only category filtering — "what do
I know about this user's travel plans" now works even if nothing was
tagged exactly "travel"."""

from __future__ import annotations

from database.connection import get_connection
from memory.schemas import MemoryCategory, MemoryRecord
from rag.embeddings import embed_passages, embed_query
from utils.errors import MemoryError_


async def insert(record: MemoryRecord) -> MemoryRecord:
    try:
        embedding = (await embed_passages([record.content]))[0]
        async with get_connection() as conn:
            cur = await conn.execute(
                """INSERT INTO memory_records (user_id, category, content, embedding, source_conversation_id, expires_at)
                   VALUES (%(uid)s, %(cat)s, %(content)s, %(emb)s, %(src)s, %(exp)s)
                   RETURNING memory_id, created_at""",
                {"uid": record.user_id, "cat": record.category.value, "content": record.content,
                 "emb": str(embedding), "src": record.source_conversation_id, "exp": record.expires_at},
            )
            row = await cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        raise MemoryError_(f"Failed to write memory record: {exc}") from exc
    return record.model_copy(update={"memory_id": row["memory_id"], "created_at": row["created_at"]})


async def list_for_user(user_id: str, category: MemoryCategory | None = None, limit: int = 50) -> list[MemoryRecord]:
    query = """SELECT memory_id, user_id, category, content, source_conversation_id, created_at, expires_at
               FROM memory_records WHERE user_id = %(uid)s AND (expires_at IS NULL OR expires_at > now())"""
    params: dict = {"uid": user_id, "limit": limit}
    if category is not None:
        query += " AND category = %(cat)s"
        params["cat"] = category.value
    query += " ORDER BY created_at DESC LIMIT %(limit)s"
    try:
        async with get_connection() as conn:
            cur = await conn.execute(query, params)
            return [MemoryRecord(**dict(r)) for r in await cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        raise MemoryError_(f"Failed to read memory records: {exc}") from exc


async def recall_semantic(user_id: str, query: str, top_k: int = 5) -> list[MemoryRecord]:
    query_embedding = await embed_query(query)
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                """SELECT memory_id, user_id, category, content, source_conversation_id, created_at, expires_at
                   FROM memory_records
                   WHERE user_id = %(uid)s AND (expires_at IS NULL OR expires_at > now())
                   ORDER BY embedding <=> %(qvec)s LIMIT %(top_k)s""",
                {"uid": user_id, "qvec": str(query_embedding), "top_k": top_k},
            )
            return [MemoryRecord(**dict(r)) for r in await cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        raise MemoryError_(f"Semantic recall failed: {exc}") from exc


async def delete(user_id: str, memory_id: int) -> None:
    try:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id = %(uid)s AND memory_id = %(mid)s",
                {"uid": user_id, "mid": memory_id},
            )
    except Exception as exc:  # noqa: BLE001
        raise MemoryError_(f"Failed to delete memory record: {exc}") from exc
