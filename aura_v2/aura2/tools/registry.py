from __future__ import annotations

from langchain_core.tools import BaseTool

from tools.calculator import calculator
from tools.calendar import calendar_create_event, calendar_delete_event, calendar_list_events
from tools.camera import camera_capture
from tools.drive import drive_delete_file, drive_list_files
from tools.gmail import gmail_create_draft, gmail_read, gmail_search, gmail_send
from tools.knowledge_base import knowledge_base_search
from tools.memory_tool import recall, remember
from tools.weather import weather
from tools.web_search import google_search
from tools.youtube import youtube_search_and_play

# Tools requiring human approval before execution — the single source of
# truth core/middleware.py's HumanInTheLoopMiddleware reads from. Anything
# with a real, external, hard-to-reverse effect belongs here.
CONSEQUENTIAL_TOOLS: set[str] = {
    "gmail_send",
    "calendar_delete_event",
    "drive_delete_file",
}


def get_tools() -> list[BaseTool]:
    return [
        calculator,
        weather,
        google_search,
        gmail_search,
        gmail_read,
        gmail_create_draft,
        gmail_send,
        calendar_create_event,
        calendar_list_events,
        calendar_delete_event,
        drive_list_files,
        drive_delete_file,
        youtube_search_and_play,
        knowledge_base_search,
        camera_capture,
        remember,
        recall,
        # NOT yet implemented — voice input happens before the agent runs
        # (STT -> text -> normal tool loop), not as a callable tool itself,
        # so there's nothing to register here for it.
    ]
