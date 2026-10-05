from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from database.connection import get_connection
from utils.errors import DatabaseError

_TITLE_MAX_LEN = 48
_STOPWORDS = {"please", "can", "you", "help", "me", "with", "the", "a", "an", "to",
              "for", "i", "need", "want", "hi", "hey", "hello"}


def generate_title(first_message: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", first_message.strip().lower())
    words = [w for w in cleaned.split() if w not in _STOPWORDS] or cleaned.split()
    title = " ".join(words[:6]).strip().capitalize() or "New Chat"
    return title[: _TITLE_MAX_LEN - 1].rstrip() + "…" if len(title) > _TITLE_MAX_LEN else title


async def create_conversation(user_id: str, first_message: str | None = None) -> dict:
    conversation_id, thread_id = str(uuid.uuid4()), str(uuid.uuid4())
    title = generate_title(first_message) if first_message else "New Chat"
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                """INSERT INTO conversations (conversation_id, user_id, thread_id, title)
                   VALUES (%(cid)s, %(uid)s, %(tid)s, %(title)s)
                   RETURNING conversation_id, user_id, thread_id, title, created_at, updated_at""",
                {"cid": conversation_id, "uid": user_id, "tid": thread_id, "title": title},
            )
            return dict(await cur.fetchone())
    except Exception as exc:  # noqa: BLE001
        raise DatabaseError(f"Failed to create conversation: {exc}") from exc


async def list_conversations(user_id: str, limit: int = 50) -> list[dict]:
    async with get_connection() as conn:
        cur = await conn.execute(
            """SELECT conversation_id, title, updated_at FROM conversations
               WHERE user_id = %(uid)s ORDER BY updated_at DESC LIMIT %(limit)s""",
            {"uid": user_id, "limit": limit},
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    async with get_connection() as conn:
        cur = await conn.execute(
            """SELECT conversation_id, user_id, thread_id, title, created_at, updated_at
               FROM conversations WHERE user_id = %(uid)s AND conversation_id = %(cid)s""",
            {"uid": user_id, "cid": conversation_id},
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def touch_conversation(user_id: str, conversation_id: str) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE conversations SET updated_at = %(now)s WHERE user_id = %(uid)s AND conversation_id = %(cid)s",
            {"uid": user_id, "cid": conversation_id, "now": datetime.now(timezone.utc)},
        )


async def set_title_if_default(user_id: str, conversation_id: str, first_message: str) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE conversations SET title = %(title)s
               WHERE user_id = %(uid)s AND conversation_id = %(cid)s AND title = 'New Chat'""",
            {"title": generate_title(first_message), "uid": user_id, "cid": conversation_id},
        )
