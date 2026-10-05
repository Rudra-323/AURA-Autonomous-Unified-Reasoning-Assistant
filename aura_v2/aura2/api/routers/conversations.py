from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user_id
from services import conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])



@router.post("")
async def new_conversation(user_id: str = Depends(get_current_user_id)) -> dict:
    return await conversation_service.create_conversation(user_id)


@router.get("")
async def list_conversations(user_id: str = Depends(get_current_user_id)) -> list[dict]:
    return await conversation_service.list_conversations(user_id)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    conv = await conversation_service.get_conversation(user_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv
