"""
Google Drive service. Uses the `drive.file` scope only (see
services/google_auth.py) — AURA can only see/manage files it created or the
user explicitly opened with it, never the user's whole Drive. This is the
least-privilege choice, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from services.google_auth import get_google_credentials
from utils.errors import AuthorizationError, ExternalServiceError
from utils.logging import get_logger

log = get_logger("services.drive")


@dataclass
class DriveFile:
    file_id: str
    name: str
    web_link: str | None


def _client(user_id: str):
    creds = get_google_credentials(user_id)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _handle_error(exc: HttpError, action: str) -> None:
    status = getattr(exc.resp, "status", None)
    if status in (401, 403):
        raise AuthorizationError(f"Drive {status} during {action}: {exc}",
                                  user_message="Drive access failed — reconnect your Google account.") from exc
    raise ExternalServiceError(f"Drive API error during {action}: {exc}",
                                user_message=f"Drive request failed ({action}).") from exc


def list_files(user_id: str, max_results: int = 10) -> list[DriveFile]:
    client = _client(user_id)
    try:
        resp = client.files().list(pageSize=max_results, fields="files(id,name,webViewLink)").execute()
    except HttpError as exc:
        _handle_error(exc, "list_files")
    return [DriveFile(file_id=f["id"], name=f["name"], web_link=f.get("webViewLink")) for f in resp.get("files", [])]


def upload_file(user_id: str, local_path: str, name: str, mime_type: str) -> DriveFile:
    client = _client(user_id)
    try:
        media = MediaFileUpload(local_path, mimetype=mime_type)
        file = client.files().create(body={"name": name}, media_body=media, fields="id,name,webViewLink").execute()
    except HttpError as exc:
        _handle_error(exc, "upload_file")
    return DriveFile(file_id=file["id"], name=file["name"], web_link=file.get("webViewLink"))


def delete_file(user_id: str, file_id: str) -> None:
    """Only reached after human approval — see CONSEQUENTIAL_TOOLS."""
    client = _client(user_id)
    try:
        client.files().delete(fileId=file_id).execute()
    except HttpError as exc:
        _handle_error(exc, "delete_file")
    log.info("drive.file_deleted", extra={"user_id": user_id, "file_id": file_id})
