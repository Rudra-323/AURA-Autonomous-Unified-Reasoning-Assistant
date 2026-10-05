"""
Middleware stack for AURA v2. Built from langchain.agents.middleware's
prebuilt classes, plus one custom middleware (GuardrailMiddleware) for
wrapping untrusted tool output (search results, email bodies, RAG chunks)
so the model always sees them clearly marked as data, not instructions.

Order matters — input-shaping middleware (PII, guardrails, summarization)
runs before control-flow middleware (limits, fallback, HITL).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
)

from langchain_core.messages import ToolMessage

try:  # LangGraph control-flow signals (interrupts etc.) must never be swallowed
    from langgraph.errors import GraphBubbleUp
except ImportError:  # pragma: no cover - defensive; import path is stable in v1
    class GraphBubbleUp(Exception):  # type: ignore[no-redef]
        pass

from config.settings import get_settings
from tools.registry import CONSEQUENTIAL_TOOLS
from utils.logging import get_logger
from utils.security import wrap_untrusted

log = get_logger("core.middleware")

# Tools whose output is external/untrusted content and should be wrapped
# before reaching the model. Internal tools (calculator) are not wrapped —
# only content that originated outside AURA's own control needs the marker.
UNTRUSTED_OUTPUT_TOOLS = {
    "google_search", "gmail_read", "gmail_search",
    "knowledge_base_search", "youtube_search_and_play",
}


def _tool_call_dict(request: Any) -> dict:
    call = getattr(request, "tool_call", None)
    return call if isinstance(call, dict) else {}


def _tool_name(request: Any) -> str | None:
    # ToolCallRequest.tool_call is a dict ({"name", "args", "id"}), and
    # ToolCallRequest.tool is the BaseTool — check both.
    name = _tool_call_dict(request).get("name")
    if name:
        return name
    return getattr(getattr(request, "tool", None), "name", None)


def _error_message(request: Any, exc: Exception) -> ToolMessage:
    """Turn an unexpected tool exception into a normal tool result the model
    can react to. Without this, one failing tool raises out of the graph and
    the user's streamed reply just dies mid-message. The technical detail is
    logged server-side only — never shown to the model or the user."""
    name = _tool_name(request) or "tool"
    log.error("tool.failed", extra={"tool": name, "error_type": type(exc).__name__}, exc_info=exc)
    return ToolMessage(
        content=(
            f"The tool '{name}' failed and could not complete the request. "
            "Briefly tell the user it didn't work and offer to try again or use another approach."
        ),
        tool_call_id=_tool_call_dict(request).get("id") or "unknown",
        name=name,
        status="error",
    )


def _wrap_if_untrusted(tool_name: str | None, response: Any) -> Any:
    """Mark external content as data. FAIL-OPEN by design: this is a
    defense-in-depth nicety, so if anything about it goes wrong we return the
    original, unwrapped result rather than break the tool call."""
    try:
        if tool_name in UNTRUSTED_OUTPUT_TOOLS and isinstance(response, ToolMessage):
            content = response.content
            if isinstance(content, str) and content:
                return response.model_copy(update={"content": wrap_untrusted(tool_name, content)})
    except Exception as exc:  # noqa: BLE001
        log.warning("guardrail.wrap_failed", extra={"tool": tool_name, "error_type": type(exc).__name__})
    return response


class GuardrailMiddleware(AgentMiddleware):
    """Tool-call safety layer:
      1. Wraps output from tools that return external/untrusted content so the
         model treats it as data, never instructions (defense-in-depth — the
         real guarantee is HumanInTheLoopMiddleware on consequential tools,
         which fires regardless of what prompted the call).
      2. Converts unexpected tool exceptions into a controlled error result.

    Both the sync and async hooks are implemented: the agent runs async
    (astream), and LangChain calls awrap_tool_call in that case — defining
    only wrap_tool_call is not enough.
    """

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            response = handler(request)
        except GraphBubbleUp:
            raise  # interrupts / control flow — not errors
        except Exception as exc:  # noqa: BLE001
            return _error_message(request, exc)
        return _wrap_if_untrusted(_tool_name(request), response)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        try:
            response = await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:  # noqa: BLE001
            return _error_message(request, exc)
        return _wrap_if_untrusted(_tool_name(request), response)


def find_orphaned_tool_calls(messages: list) -> dict[str, str]:
    """Return {tool_call_id: tool_name} for every tool call an AIMessage made
    that has no matching ToolMessage anywhere later in the list.

    This is how a conversation gets permanently stuck: if a tool call's
    response is ever lost (a crash between the model call and tool
    execution, a bug in earlier middleware, anything), every future turn in
    that thread re-sends the same broken history to the provider, which
    rejects it outright — 'assistant message with tool_calls must be
    followed by tool messages'. Detecting it here means we can repair it
    on the next turn instead of the thread being dead forever.
    """
    pending: dict[str, str] = {}
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                pending[tc["id"]] = tc.get("name", "tool")
        if isinstance(msg, ToolMessage):
            pending.pop(msg.tool_call_id, None)
    return pending


def _repair_messages(state: dict) -> dict[str, Any] | None:
    messages = state.get("messages", [])
    orphaned = find_orphaned_tool_calls(messages)
    if not orphaned:
        return None
    log.warning("middleware.repairing_orphaned_tool_calls", extra={"tool_call_ids": list(orphaned)})
    synthetic = [
        ToolMessage(
            content=(
                f"(System note: the result of this '{name}' call was lost, likely due to an "
                "earlier error. Please retry the action if it's still needed.)"
            ),
            tool_call_id=call_id,
            name=name,
            status="error",
        )
        for call_id, name in orphaned.items()
    ]
    # New message objects with fresh IDs -> the add_messages reducer appends
    # them rather than replacing anything already in state.
    return {"messages": synthetic}


class HistoryRepairMiddleware(AgentMiddleware):
    """Runs before every model call. Self-healing: fixes an already-broken
    conversation on its very next turn, not just future ones — the user does
    not need to start a new chat for this to take effect."""

    def before_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        return _repair_messages(state)

    async def abefore_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        return _repair_messages(state)


def build_middleware_stack(*, primary_model, fallback_model) -> list:
    settings = get_settings()

    interrupt_on = {
        tool_name: {
            "allowed_decisions": ["approve", "edit", "reject"],
            "description": f"AURA wants to run '{tool_name}'. Review the exact arguments below before approving.",
        }
        for tool_name in CONSEQUENTIAL_TOOLS
    }

    return [
        HistoryRepairMiddleware(),
        PIIMiddleware("email", strategy="mask", apply_to_input=True),
        GuardrailMiddleware(),
        SummarizationMiddleware(
            # An already-configured ChatOpenAI instance (routed through
            # OpenRouter), NOT a bare model-name string. SummarizationMiddleware
            # calls init_chat_model() on a string, which tries to infer a
            # provider from the name — OpenRouter's "vendor/model" naming
            # doesn't match any provider LangChain recognizes, and even if it
            # did, that path would build a fresh client with default
            # credentials, bypassing our OpenRouter api_key/base_url entirely.
            model=primary_model,
            messages_to_keep=settings.summarization_keep_messages,
        ),
        ModelCallLimitMiddleware(run_limit=settings.max_model_calls_per_run, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=settings.max_tool_calls_per_run, exit_behavior="end"),
        ModelFallbackMiddleware(fallback_model),
        HumanInTheLoopMiddleware(
            interrupt_on=interrupt_on,
            description_prefix="Approval required before AURA takes this action",
        ),
    ]
