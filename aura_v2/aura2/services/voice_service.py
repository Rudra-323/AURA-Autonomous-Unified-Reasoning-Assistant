"""
Voice turn orchestration: audio in -> transcript -> agent (existing
streaming path) -> synthesized audio out.

Originally this synthesized sentence-by-sentence as tokens streamed in, to
minimize time-to-first-audio. In practice that produced many tiny separate
audio clips (e.g. 13 for one reply with a numbered list) — and Streamlit's
st.audio() widgets don't auto-play in sequence, so the result was the user
having to manually click "play" over and over, which is worse than just
waiting. Streamlit's rerun-per-interaction model isn't well-suited to
gapless multi-clip audio playback; a custom frontend with a real audio
queue could revisit true sentence-streamed TTS later (see architecture.md).
For now: buffer the full reply, then synthesize ONE clip and autoplay it —
slightly higher latency to first sound, much better actual experience.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import AsyncIterator

from core.context import AgentContext
from services import agent_service
from voice.tts import synthesize
from voice.stt import transcribe

_AUDIO_OUT_DIR = Path("/tmp/aura_voice_out")


def transcribe_user_audio(audio_path: str, language: str) -> str:
    return transcribe(audio_path, language)


async def transcribe_user_audio_async(audio_path: str, language: str) -> str:
    """Async wrapper for API routes — transcribe() is sync/CPU-bound model
    inference, so run it off the event loop."""
    import asyncio
    return await asyncio.to_thread(transcribe, audio_path, language)


async def stream_voice_reply(*, context: AgentContext, user_message: str) -> AsyncIterator[dict]:
    """Wraps agent_service.stream_turn: text still streams token-by-token
    (for live display), but speech is synthesized once, after the full
    reply is known, as a single playable clip."""
    buffer = ""
    async for event in agent_service.stream_turn(context=context, user_message=user_message):
        if event["type"] == "token":
            buffer += event["content"]
        yield event

    if buffer.strip():
        yield await _synthesize_chunk(buffer, context.language)


async def _synthesize_chunk(text: str, language: str) -> dict:
    _AUDIO_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = str(_AUDIO_OUT_DIR / f"{uuid.uuid4()}.mp3")
    await synthesize(text, language, out_path)
    return {"type": "audio_chunk", "text": text, "audio_path": out_path}
