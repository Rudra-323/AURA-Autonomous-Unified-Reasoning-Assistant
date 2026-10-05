"""
Gmail tools. user_id comes from ToolRuntime.context (injected by LangGraph
from the AgentContext passed at agent.ainvoke(..., context=...) time) —
never from a tool argument the model could set itself. This is what makes
per-user isolation actually hold: the model cannot impersonate another user
by passing a different user_id, because it never sees or controls this
value at all.

gmail_send has no special handling here — the approval pause is enforced
one layer up by HumanInTheLoopMiddleware intercepting calls to a tool named
"gmail_send" before this function ever runs (see core/middleware.py).
"""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from core.context import AgentContext
from services import gmail_service
from utils.errors import AuraError
from utils.logging import get_logger

log = get_logger("tools.gmail")


@tool
def gmail_search(query: str, runtime: ToolRuntime[AgentContext], max_results: int = 10) -> str:
    """Search the user's Gmail using Gmail search syntax, e.g.
    "from:john subject:invoice" or "is:unread newer_than:2d"."""
    try:
        results = gmail_service.search(runtime.context.user_id, query, max_results=max_results)
    except AuraError as exc:
        log.warning("gmail_search.failed", extra={"error": str(exc)})
        return f"Gmail search failed: {exc.user_message}"
    if not results:
        return "No matching messages found."
    return "\n".join(
        f"- id={r.message_id} from={r.sender} subject={r.subject!r} snippet={r.snippet!r}" for r in results
    )


@tool
def gmail_read(message_id: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Read the full content of a Gmail message by ID (from gmail_search)."""
    try:
        msg = gmail_service.read(runtime.context.user_id, message_id)
    except AuraError as exc:
        log.warning("gmail_read.failed", extra={"error": str(exc)})
        return f"Could not read message: {exc.user_message}"
    return f"From: {msg.sender}\nTo: {msg.to}\nSubject: {msg.subject}\n\n{msg.body}"


@tool
def gmail_create_draft(to: str, subject: str, body: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Create a Gmail draft (does NOT send it)."""
    try:
        result = gmail_service.create_draft(runtime.context.user_id, to, subject, body)
    except AuraError as exc:
        log.warning("gmail_draft.failed", extra={"error": str(exc)})
        return f"Could not create draft: {exc.user_message}"
    return f"Draft created (draft_id={result.draft_id}). It has NOT been sent."


@tool
def gmail_send(to: str, subject: str, body: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Send an email immediately via Gmail. Irreversible — the system
    pauses for human approval (showing the exact To/Subject/Body) before
    this ever executes; you don't need to ask the user to confirm yourself."""
    try:
        result = gmail_service.send(runtime.context.user_id, to, subject, body)
    except AuraError as exc:
        log.warning("gmail_send.failed", extra={"error": str(exc)})
        return f"Send failed: {exc.user_message}"
    return f"Email sent to {to} (message_id={result.message_id})."
