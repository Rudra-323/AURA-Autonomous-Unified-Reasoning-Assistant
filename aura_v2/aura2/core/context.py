"""
Typed context threaded through every agent run. Identity/authorization is
never inferred by the LLM — it's constructed by the service layer from the
authenticated request and passed into the LangGraph runtime config.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    user_id: str
    conversation_id: str
    thread_id: str
    timezone: str = "UTC"
    language: str = "en"  # "en" | "hi" | "or" — drives voice STT/TTS routing and response language
