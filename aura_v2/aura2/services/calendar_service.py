"""Google Calendar service — same per-user credential pattern as Gmail."""

from __future__ import annotations

from dataclasses import dataclass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from services.google_auth import get_google_credentials
from utils.errors import AuthorizationError, ExternalServiceError
from utils.logging import get_logger

log = get_logger("services.calendar")


@dataclass
class CalendarEvent:
    event_id: str
    summary: str
    start: str
    end: str
    meet_link: str | None


def _client(user_id: str):
    creds = get_google_credentials(user_id)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _handle_error(exc: HttpError, action: str) -> None:
    status = getattr(exc.resp, "status", None)
    if status in (401, 403):
        raise AuthorizationError(f"Calendar {status} during {action}: {exc}",
                                  user_message="Calendar access failed — reconnect your Google account.") from exc
    raise ExternalServiceError(f"Calendar API error during {action}: {exc}",
                                user_message=f"Calendar request failed ({action}).") from exc


def create_event(user_id: str, summary: str, start_iso: str, end_iso: str,
                  description: str = "", add_meet: bool = False) -> CalendarEvent:
    client = _client(user_id)
    body = {
        "summary": summary, "description": description,
        "start": {"dateTime": start_iso}, "end": {"dateTime": end_iso},
    }
    if add_meet:
        body["conferenceData"] = {"createRequest": {"requestId": f"aura-{summary[:20]}"}}
    try:
        event = client.events().insert(
            calendarId="primary", body=body, conferenceDataVersion=1 if add_meet else 0
        ).execute()
    except HttpError as exc:
        _handle_error(exc, "create_event")
    meet_link = event.get("hangoutLink")
    return CalendarEvent(event_id=event["id"], summary=event["summary"],
                          start=event["start"].get("dateTime", ""), end=event["end"].get("dateTime", ""),
                          meet_link=meet_link)


def list_events(user_id: str, time_min_iso: str, time_max_iso: str, max_results: int = 10) -> list[CalendarEvent]:
    client = _client(user_id)
    try:
        resp = client.events().list(
            calendarId="primary", timeMin=time_min_iso, timeMax=time_max_iso,
            maxResults=max_results, singleEvents=True, orderBy="startTime",
        ).execute()
    except HttpError as exc:
        _handle_error(exc, "list_events")
    return [
        CalendarEvent(event_id=e["id"], summary=e.get("summary", "(no title)"),
                      start=e["start"].get("dateTime", e["start"].get("date", "")),
                      end=e["end"].get("dateTime", e["end"].get("date", "")),
                      meet_link=e.get("hangoutLink"))
        for e in resp.get("items", [])
    ]


def delete_event(user_id: str, event_id: str) -> None:
    """Only reached after human approval — see CONSEQUENTIAL_TOOLS."""
    client = _client(user_id)
    try:
        client.events().delete(calendarId="primary", eventId=event_id).execute()
    except HttpError as exc:
        _handle_error(exc, "delete_event")
    log.info("calendar.event_deleted", extra={"user_id": user_id, "event_id": event_id})
