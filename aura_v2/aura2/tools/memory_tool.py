"""
Long-term memory tools. TEMPORARY-category memories get a 24h expiry and
are never auto-promoted to a permanent category — see memory/schemas.py.
The model decides *when* something is worth remembering (per the system
prompt's memory policy); this tool just enforces the category contract.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langchain.tools import ToolRuntime, tool

from core.context import AgentContext
from memory import repositories
from memory.schemas import MemoryCategory, MemoryRecord
from utils.errors import AuraError
from utils.logging import get_logger

log = get_logger("tools.memory")

_TEMPORARY_TTL = timedelta(hours=24)


@tool
async def remember(content: str, category: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Save a durable fact/preference about the user to long-term memory.
    Only use this for things that are true beyond this single conversation
    (e.g. "prefers concise answers", "works as a data engineer") — not
    one-off task details.

    Args:
        content: The fact to remember, in plain text.
        category: One of FACT, PREFERENCE, PROFILE, TASK, CONTEXT, TEMPORARY.
    """
    try:
        cat = MemoryCategory(category.upper())
    except ValueError:
        return f"Invalid category '{category}'. Use one of: {', '.join(c.value for c in MemoryCategory)}."

    expires_at = datetime.now(timezone.utc) + _TEMPORARY_TTL if cat == MemoryCategory.TEMPORARY else None
    try:
        await repositories.insert(MemoryRecord(
            user_id=runtime.context.user_id, category=cat, content=content,
            source_conversation_id=runtime.context.conversation_id, expires_at=expires_at,
        ))
    except AuraError as exc:
        log.warning("memory.remember_failed", extra={"error": str(exc)})
        return f"Couldn't save that to memory: {exc.user_message}"
    return "Remembered."


@tool
async def recall(query: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Recall relevant long-term facts/preferences about the user, using
    semantic search — not just exact keyword matches. Use this when
    answering might benefit from something remembered about the user
    earlier, in a different conversation."""
    try:
        results = await repositories.recall_semantic(runtime.context.user_id, query)
    except AuraError as exc:
        log.warning("memory.recall_failed", extra={"error": str(exc)})
        return f"Couldn't search memory: {exc.user_message}"
    if not results:
        return "Nothing relevant found in memory."
    return "\n".join(f"- [{r.category.value}] {r.content}" for r in results)
