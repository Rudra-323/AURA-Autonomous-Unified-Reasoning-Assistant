from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from core.context import AgentContext
from services import drive_service
from utils.errors import AuraError

_DRIVE_DIR = "storage/drive_uploads"  # local staging before upload; see services/media_service.py


@tool
def drive_list_files(runtime: ToolRuntime[AgentContext], max_results: int = 10) -> str:
    """List files in the user's AURA-managed Drive space."""
    try:
        files = drive_service.list_files(runtime.context.user_id, max_results)
    except AuraError as exc:
        return f"Could not list Drive files: {exc.user_message}"
    if not files:
        return "No files found."
    return "\n".join(f"- id={f.file_id} {f.name} ({f.web_link})" for f in files)


@tool
def drive_delete_file(file_id: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Delete a file from Drive by ID. Irreversible — requires human
    approval before this executes."""
    try:
        drive_service.delete_file(runtime.context.user_id, file_id)
    except AuraError as exc:
        return f"Could not delete file: {exc.user_message}"
    return f"File {file_id} deleted."
