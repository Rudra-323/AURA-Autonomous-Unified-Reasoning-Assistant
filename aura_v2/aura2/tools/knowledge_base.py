from __future__ import annotations

from langchain.tools import ToolRuntime, tool

from core.context import AgentContext
from rag.retriever import hybrid_search
from utils.errors import AuraError
from utils.logging import get_logger

log = get_logger("tools.knowledge_base")


@tool
async def knowledge_base_search(query: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Search the user's own uploaded documents (PDFs, Word docs, spreadsheets)
    for relevant content. Use this whenever the user asks about something
    that could be in a document they've uploaded — never guess at document
    contents otherwise."""
    try:
        results = await hybrid_search(runtime.context.user_id, query)
    except AuraError as exc:
        log.warning("knowledge_base_search.failed", extra={"error": str(exc)})
        return f"Document search failed: {exc.user_message}"
    if not results:
        return "No relevant content found in your uploaded documents."
    return "\n\n".join(f"[from document {r['document_id']}]\n{r['content']}" for r in results)
