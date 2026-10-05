"""
The only module that calls the compiled agent directly. API routers talk to
this, never to langgraph/langchain directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from core.agent import get_agent
from core.context import AgentContext
from schemas.tool import PendingApproval
from utils.errors import ApprovalError
from utils.logging import get_logger
from utils.media_markers import PLAY_MEDIA, REQUEST_CAMERA, find_marker

log = get_logger("services.agent")


@dataclass
class TurnResult:
    reply: str | None
    pending_approval: PendingApproval | None


def _run_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _extract_pending_approval(result: dict) -> PendingApproval | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    payload = interrupts[0].value
    action_requests = payload.get("action_requests", [])
    review_configs = payload.get("review_configs", [])
    if not action_requests:
        return None
    action = action_requests[0]
    review = review_configs[0] if review_configs else {}
    return PendingApproval(
        tool_name=action.get("name", "unknown_tool"),
        action_label=action.get("description", f"Run {action.get('name', 'a tool')}"),
        args=action.get("arguments") or action.get("args") or {},
        allowed_decisions=review.get("allowed_decisions", ["approve", "reject"]),
    )


def _pending_approval_event(state) -> dict | None:
    if not state or not state.tasks:
        return None
    for task in state.tasks:
        if not task.interrupts:
            continue
        payload = task.interrupts[0].value
        action_requests = payload.get("action_requests", [])
        if not action_requests:
            continue
        action = action_requests[0]
        review = (payload.get("review_configs") or [{}])[0]
        return {
            "type": "approval_required",
            "tool_name": action.get("name", "unknown_tool"),
            "args": action.get("arguments") or action.get("args") or {},
            "allowed_decisions": review.get("allowed_decisions", ["approve", "reject"]),
        }
    return None


def _unresolved_tool_calls(messages: list) -> list[tuple[str, str]]:
    responded_to = {
        message.tool_call_id
        for message in messages
        if getattr(message, "type", None) == "tool"
        and getattr(message, "tool_call_id", None)
    }
    unresolved = []
    seen = set()
    for message in messages:
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", []) or []:
            call_id = call.get("id")
            if call_id and call_id not in responded_to and call_id not in seen:
                unresolved.append((call_id, call.get("name") or "tool"))
                seen.add(call_id)
    return unresolved


async def _prepare_turn(agent, config: dict) -> dict | None:
    """Keep new model requests from inheriting malformed or paused history."""
    state = await agent.aget_state(config)
    pending = _pending_approval_event(state)
    if pending:
        return pending
    if not state or not state.values:
        return None

    unresolved = _unresolved_tool_calls(state.values.get("messages", []))
    if unresolved:
        await agent.aupdate_state(config, {
            "messages": [
                ToolMessage(
                    content=(
                        "No result was recorded for this tool call, so its outcome is unknown. "
                        "Do not retry it automatically; explain this and ask the user to verify "
                        "the outcome before trying again."
                    ),
                    tool_call_id=call_id,
                    name=tool_name,
                    status="error",
                )
                for call_id, tool_name in unresolved
            ]
        })
        log.warning(
            "agent.orphaned_tool_calls_recovered",
            extra={"count": len(unresolved)},
        )
    return None


def _extract_reply(result: dict) -> str | None:
    for message in reversed(result.get("messages", [])):
        if getattr(message, "type", None) == "ai" and getattr(message, "content", None):
            content = message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(b.get("text", "") for b in content if isinstance(b, dict)) or None
    return None


async def run_turn(*, context: AgentContext, user_message: str) -> TurnResult:
    agent = get_agent()
    pending_event = await _prepare_turn(agent, _run_config(context.thread_id))
    if pending_event:
        return TurnResult(
            reply=None,
            pending_approval=PendingApproval(
                tool_name=pending_event["tool_name"],
                action_label=f"Run {pending_event['tool_name']}",
                args=pending_event["args"],
                allowed_decisions=pending_event["allowed_decisions"],
            ),
        )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config=_run_config(context.thread_id), context=context,
    )
    pending = _extract_pending_approval(result)
    if pending:
        log.info("agent.approval_required", extra={"tool": pending.tool_name})
        return TurnResult(reply=None, pending_approval=pending)
    return TurnResult(reply=_extract_reply(result), pending_approval=None)


async def stream_turn(*, context: AgentContext, user_message: str) -> AsyncIterator[dict]:
    """Yields small dicts the API layer turns into SSE events:
    {"type": "token", "content": "..."} for streamed text,
    {"type": "approval_required", ...} if the run pauses on HITL,
    {"type": "done"} at the end.

    NOTE: mixing token streaming with mid-stream HITL interrupts is a newer
    corner of the LangGraph streaming API — the "check final state after the
    stream ends" approach below is a safe, verified-to-work fallback, but if
    your LangGraph version surfaces __interrupt__ directly in the "custom"
    stream_mode, prefer catching it there for lower latency (the agent would
    otherwise keep streaming tokens for the tool-call message before you see
    the pause). Smoke-test this against a real gmail_send call before
    treating it as final."""
    agent = get_agent()
    config = _run_config(context.thread_id)
    pending_event = await _prepare_turn(agent, config)
    if pending_event:
        yield pending_event
        yield {
            "type": "error",
            "message": (
                "A previous action still needs approval. This message was not processed; "
                "resolve the approval, then send it again."
            ),
        }
        return

    async for stream_type, chunk in agent.astream(
        {"messages": [{"role": "user", "content": user_message}]},
        config=config, context=context, stream_mode=["messages", "custom"],
    ):
        if stream_type == "messages":
            message_chunk, metadata = chunk
            content = getattr(message_chunk, "content", None)
            msg_type = getattr(message_chunk, "type", None)

            # Tool results aren't part of the model's own text stream, but
            # camera/youtube need their raw marker output — not whatever the
            # model paraphrases it as — to drive UI behavior reliably.
            if msg_type == "tool" and isinstance(content, str):
                play = find_marker(content, PLAY_MEDIA)
                if play:
                    yield {"type": "play_media", "video_id": play.get("video_id", ""),
                           "title": play.get("title", ""), "embed_url": play.get("embed_url", "")}
                camera = find_marker(content, REQUEST_CAMERA)
                if camera:
                    yield {"type": "request_camera", "label": camera.get("label", "Take a photo")}
                continue

            if content and metadata.get("langgraph_node") == "model":
                yield {"type": "token", "content": content if isinstance(content, str) else str(content)}

    # After the stream ends, check final state for a pending interrupt —
    # astream's "messages" mode doesn't surface __interrupt__ directly, so
    # we read graph state once the stream completes.
    state = await agent.aget_state(config)
    pending_event = _pending_approval_event(state)
    if pending_event:
        yield pending_event
        return
    yield {"type": "done"}


async def resume_with_decision(*, context: AgentContext, tool_name: str, decision_type: str,
                                edited_args: dict | None = None, message: str | None = None) -> TurnResult:
    if decision_type not in {"approve", "edit", "reject"}:
        raise ApprovalError(f"Unsupported decision type: {decision_type}")

    decision: dict = {"type": decision_type}
    if decision_type == "edit":
        if not edited_args:
            raise ApprovalError("edit decision requires edited_args")
        decision["edited_action"] = {"name": tool_name, "args": edited_args}
    if decision_type == "reject" and message:
        decision["message"] = message

    agent = get_agent()
    result = await agent.ainvoke(
        Command(resume={"decisions": [decision]}), config=_run_config(context.thread_id), context=context,
    )
    pending = _extract_pending_approval(result)
    if pending:
        return TurnResult(reply=None, pending_approval=pending)
    return TurnResult(reply=_extract_reply(result), pending_approval=None)


async def get_message_history(*, thread_id: str) -> list[dict]:
    agent = get_agent()
    state = await agent.aget_state(_run_config(thread_id))
    if not state or not state.values:
        return []
    history = []
    for message in state.values.get("messages", []):
        role = getattr(message, "type", None)
        content = getattr(message, "content", None)
        if role not in {"human", "ai"} or not content:
            continue
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
        history.append({"role": "user" if role == "human" else "assistant", "content": content})
    return history
