"""
Gmail API service. Knows Gmail's wire format; knows nothing about LangChain.
Every method takes user_id explicitly so a service instance is safely
shareable across concurrent requests for different users (no per-user
mutable state held here).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from services.google_auth import get_google_credentials
from utils.errors import AuthorizationError, ExternalServiceError
from utils.logging import get_logger

log = get_logger("services.gmail")


@dataclass
class EmailSummary:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    snippet: str


@dataclass
class EmailMessage:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    to: str
    body: str


@dataclass
class DraftResult:
    draft_id: str
    message_id: str


@dataclass
class SendResult:
    message_id: str
    thread_id: str


def _client(user_id: str):
    creds = get_google_credentials(user_id)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _handle_http_error(exc: HttpError, action: str) -> None:
    status = getattr(exc.resp, "status", None)
    if status in (401, 403):
        raise AuthorizationError(
            f"Gmail {status} during {action}: {exc}",
            user_message="Gmail access failed — reconnect your Google account or check permissions.",
        ) from exc
    raise ExternalServiceError(
        f"Gmail API error during {action}: {exc}",
        user_message=f"Gmail request failed ({action}). Please try again.",
    ) from exc


def _extract_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        body = _extract_body(part)
        if body:
            return body
    return ""


def _build_mime_message(to: str, subject: str, body: str) -> dict:
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")}


def search(user_id: str, query: str, max_results: int = 10) -> list[EmailSummary]:
    client = _client(user_id)
    try:
        resp = client.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    except HttpError as exc:
        _handle_http_error(exc, "search")

    summaries: list[EmailSummary] = []
    for item in resp.get("messages", []):
        msg = client.users().messages().get(
            userId="me", id=item["id"], format="metadata", metadataHeaders=["Subject", "From"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        summaries.append(EmailSummary(
            message_id=msg["id"], thread_id=msg["threadId"],
            subject=headers.get("Subject", "(no subject)"), sender=headers.get("From", "(unknown)"),
            snippet=msg.get("snippet", ""),
        ))
    return summaries


def read(user_id: str, message_id: str) -> EmailMessage:
    client = _client(user_id)
    try:
        msg = client.users().messages().get(userId="me", id=message_id, format="full").execute()
    except HttpError as exc:
        _handle_http_error(exc, "read")

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return EmailMessage(
        message_id=msg["id"], thread_id=msg["threadId"],
        subject=headers.get("Subject", "(no subject)"), sender=headers.get("From", "(unknown)"),
        to=headers.get("To", "(unknown)"), body=_extract_body(msg.get("payload", {})),
    )


def create_draft(user_id: str, to: str, subject: str, body: str) -> DraftResult:
    client = _client(user_id)
    try:
        draft = client.users().drafts().create(
            userId="me", body={"message": _build_mime_message(to, subject, body)}
        ).execute()
    except HttpError as exc:
        _handle_http_error(exc, "create_draft")
    return DraftResult(draft_id=draft["id"], message_id=draft["message"]["id"])


def send(user_id: str, to: str, subject: str, body: str) -> SendResult:
    """Only ever reached after human approval — see core/middleware.py's
    HumanInTheLoopMiddleware + tools/registry.CONSEQUENTIAL_TOOLS."""
    client = _client(user_id)
    try:
        sent = client.users().messages().send(
            userId="me", body=_build_mime_message(to, subject, body)
        ).execute()
    except HttpError as exc:
        _handle_http_error(exc, "send")
    log.info("gmail.sent", extra={"user_id": user_id, "message_id": sent["id"]})
    return SendResult(message_id=sent["id"], thread_id=sent["threadId"])
