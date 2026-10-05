from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from core.context import AgentContext
from services import calendar_service
from utils.errors import AuraError
from utils.logging import get_logger

log = get_logger("tools.calendar")


@tool
def calendar_create_event(
    summary: str, start_iso: str, end_iso: str, runtime: ToolRuntime[AgentContext],
    description: str = "", add_meet: bool = False,
) -> str:
    """Create a calendar event. start_iso/end_iso must be RFC3339 datetimes
    (e.g. "2026-10-01T15:00:00+05:30"). Set add_meet=True to attach a Google
    Meet link."""
    try:
        event = calendar_service.create_event(
            runtime.context.user_id, summary, start_iso, end_iso, description, add_meet
        )
    except AuraError as exc:
        return f"Could not create event: {exc.user_message}"
    meet = f" Meet link: {event.meet_link}" if event.meet_link else ""
    return f"Created '{event.summary}' ({event.start} to {event.end}).{meet}"


@tool
def calendar_list_events(time_min_iso: str, time_max_iso: str, runtime: ToolRuntime[AgentContext]) -> str:
    """List events between two RFC3339 datetimes."""
    try:
        events = calendar_service.list_events(runtime.context.user_id, time_min_iso, time_max_iso)
    except AuraError as exc:
        return f"Could not list events: {exc.user_message}"
    if not events:
        return "No events found in that range."
    return "\n".join(f"- id={e.event_id} {e.summary}: {e.start} to {e.end}" for e in events)


@tool
def calendar_delete_event(event_id: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Delete a calendar event by ID. Irreversible — requires human approval
    before this executes, same pattern as gmail_send."""
    try:
        calendar_service.delete_event(runtime.context.user_id, event_id)
    except AuraError as exc:
        return f"Could not delete event: {exc.user_message}"
    return f"Event {event_id} deleted."
