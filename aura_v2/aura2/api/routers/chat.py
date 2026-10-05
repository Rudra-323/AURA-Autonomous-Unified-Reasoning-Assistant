from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from api.deps import get_current_user_id
from core.context import AgentContext
from services import agent_service, conversation_service
from utils.logging import get_logger

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger("api.chat")


class SendMessageRequest(BaseModel):
    conversation_id: str
    message: str
    language: str = "en"


class ResumeRequest(BaseModel):
    conversation_id: str
    tool_name: str
    decision_type: str  # "approve" | "edit" | "reject"
    edited_args: dict | None = None
    message: str | None = None


async def _build_context(user_id: str, conversation_id: str, language: str) -> AgentContext:
    conv = await conversation_service.get_conversation(user_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return AgentContext(user_id=user_id, conversation_id=conversation_id, thread_id=conv["thread_id"], language=language)


@router.post("/stream")
async def stream_chat(body: SendMessageRequest, user_id: str = Depends(get_current_user_id)):
    context = await _build_context(user_id, body.conversation_id, body.language)

    is_first = len(await agent_service.get_message_history(thread_id=context.thread_id)) == 0
    if is_first:
        await conversation_service.set_title_if_default(user_id, body.conversation_id, body.message)

    async def event_generator():
        try:
            async for event in agent_service.stream_turn(context=context, user_message=body.message):
                yield {"event": event["type"], "data": json.dumps(event)}
            await conversation_service.touch_conversation(user_id, body.conversation_id)
        except Exception:  # noqa: BLE001
            # Without this, any failure mid-run kills the SSE connection and the
            # client just sees "peer closed connection". Log the full traceback
            # server-side; send the client a short, readable error event instead.
            log.exception("chat.stream_failed", extra={"conversation_id": body.conversation_id})
            yield {"event": "error", "data": json.dumps({
                "type": "error",
                "message": "Something went wrong while AURA was working on that. Please try again.",
            })}

    return EventSourceResponse(event_generator())


@router.post("/resume")
async def resume_chat(body: ResumeRequest, user_id: str = Depends(get_current_user_id)) -> dict:
    context = await _build_context(user_id, body.conversation_id, "en")
    result = await agent_service.resume_with_decision(
        context=context, tool_name=body.tool_name, decision_type=body.decision_type,
        edited_args=body.edited_args, message=body.message,
    )
    await conversation_service.touch_conversation(user_id, body.conversation_id)
    if result.pending_approval:
        return {"pending_approval": result.pending_approval.model_dump()}
    return {"reply": result.reply}


@router.get("/{conversation_id}/history")
async def get_history(conversation_id: str, user_id: str = Depends(get_current_user_id)) -> list[dict]:
    conv = await conversation_service.get_conversation(user_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return await agent_service.get_message_history(thread_id=conv["thread_id"])
