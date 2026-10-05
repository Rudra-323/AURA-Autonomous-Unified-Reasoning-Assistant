"""
Voice endpoints. The browser records audio (native mic permission prompt —
same consent model as camera, see media.py) and POSTs the file here.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse
import json

from api.deps import get_current_user_id
from api.routers.chat import _build_context
from services import conversation_service, voice_service
from utils.errors import AuraError
from utils.logging import get_logger

router = APIRouter(prefix="/voice", tags=["voice"])
log = get_logger("api.voice")


@router.post("/message")
async def voice_message(
    conversation_id: str = Form(...),
    language: str = Form("en"),
    audio: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """Transcribes the uploaded audio, then streams the agent's reply as both
    text tokens and synthesized audio chunks (SSE)."""
    context = await _build_context(user_id, conversation_id, language)

    with tempfile.NamedTemporaryFile(suffix=Path(audio.filename or "audio.wav").suffix, delete=False) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name

    try:
        transcript = await voice_service.transcribe_user_audio_async(tmp_path, language)
    except AuraError as exc:
        raise HTTPException(status_code=502, detail=exc.user_message) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Couldn't understand the audio — please try again.")

    async def event_generator():
        yield {"event": "transcript", "data": json.dumps({"text": transcript})}
        try:
            async for event in voice_service.stream_voice_reply(context=context, user_message=transcript):
                yield {"event": event["type"], "data": json.dumps(event)}
            await conversation_service.touch_conversation(user_id, conversation_id)
        except Exception:  # noqa: BLE001
            log.exception("voice.stream_failed", extra={"conversation_id": conversation_id})
            yield {"event": "error", "data": json.dumps({
                "type": "error",
                "message": "Something went wrong with the voice reply. Please try again.",
            })}

    return EventSourceResponse(event_generator())
