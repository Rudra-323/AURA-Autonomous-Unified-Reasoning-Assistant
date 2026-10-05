"""
The UI is a pure client of the API — it never imports core/services/tools
directly (spec: UI -> Services -> Agent, never UI -> Agent). Everything here
is plain HTTP/SSE against api/main.py.
"""

from __future__ import annotations

import os
from typing import Iterator

import httpx

API_BASE_URL = os.environ.get("AURA_API_URL", "http://localhost:8000")


def _headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def signup(email: str, password: str, display_name: str = "") -> dict:
    resp = httpx.post(f"{API_BASE_URL}/auth/signup",
                       json={"email": email, "password": password, "display_name": display_name})
    resp.raise_for_status()
    return resp.json()


def login(email: str, password: str) -> dict:
    resp = httpx.post(f"{API_BASE_URL}/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()


def list_conversations(token: str) -> list[dict]:
    resp = httpx.get(f"{API_BASE_URL}/conversations", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def create_conversation(token: str) -> dict:
    resp = httpx.post(f"{API_BASE_URL}/conversations", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def get_history(token: str, conversation_id: str) -> list[dict]:
    resp = httpx.get(f"{API_BASE_URL}/chat/{conversation_id}/history", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def _parse_sse(response: httpx.Response) -> Iterator[tuple[str, str]]:
    """Minimal text/event-stream parser: yields (event, data) pairs. Avoids
    adding an extra SSE-client dependency for a format this simple."""
    event, data_lines = "message", []
    for line in response.iter_lines():
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = "message", []
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())


def stream_chat(token: str, conversation_id: str, message: str, language: str = "en") -> Iterator[tuple[str, str]]:
    with httpx.stream(
        "POST", f"{API_BASE_URL}/chat/stream", headers=_headers(token), timeout=120.0,
        json={"conversation_id": conversation_id, "message": message, "language": language},
    ) as response:
        response.raise_for_status()
        yield from _parse_sse(response)


def resume_decision(token: str, conversation_id: str, tool_name: str, decision_type: str,
                     edited_args: dict | None = None, message: str | None = None) -> dict:
    resp = httpx.post(
        f"{API_BASE_URL}/chat/resume", headers=_headers(token),
        json={"conversation_id": conversation_id, "tool_name": tool_name, "decision_type": decision_type,
              "edited_args": edited_args, "message": message},
    )
    resp.raise_for_status()
    return resp.json()


def upload_document(token: str, file_bytes: bytes, filename: str, content_type: str) -> dict:
    resp = httpx.post(
        f"{API_BASE_URL}/documents/upload", headers=_headers(token),
        files={"file": (filename, file_bytes, content_type)},
    )
    resp.raise_for_status()
    return resp.json()


def get_ingestion_status(token: str, job_id: str) -> dict:
    resp = httpx.get(f"{API_BASE_URL}/documents/jobs/{job_id}", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def save_photo(token: str, image_bytes: bytes) -> dict:
    resp = httpx.post(
        f"{API_BASE_URL}/media/save-photo", headers=_headers(token),
        files={"photo": ("photo.jpg", image_bytes, "image/jpeg")},
    )
    resp.raise_for_status()
    return resp.json()


def voice_message(token: str, conversation_id: str, audio_bytes: bytes, language: str) -> Iterator[tuple[str, str]]:
    with httpx.stream(
        "POST", f"{API_BASE_URL}/voice/message", headers=_headers(token), timeout=120.0,
        data={"conversation_id": conversation_id, "language": language},
        files={"audio": ("audio.wav", audio_bytes, "audio/wav")},
    ) as response:
        response.raise_for_status()
        yield from _parse_sse(response)
