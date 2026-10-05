"""
Google OAuth, per-user. v1 stored a single shared token.json; v2 must
isolate tokens per user_id since multiple people can now use AURA — each
user authorizes their OWN Gmail/Calendar/Drive access, tokens are never
shared across accounts.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config.settings import get_settings
from utils.errors import AuthenticationError
from utils.logging import get_logger

log = get_logger("services.google_auth")

# Least-privilege, additive scopes. Add Drive/Calendar scopes here only —
# never widen to a broad scope like "mail.google.com" or full Drive access.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.file",  # per-file access only, not full Drive
]


def _token_path(user_id: str) -> Path:
    settings = get_settings()
    return Path(settings.google_token_dir) / f"{user_id}.json"


def get_google_credentials(user_id: str, *, run_local_server: bool = False) -> Credentials:
    """Returns valid credentials for this specific user. In a real deployed
    multi-user app, `run_local_server=True` only makes sense for local dev —
    production must use a proper web OAuth redirect flow (authorization URL
    + callback endpoint), not a local browser popup. That web flow is the
    next piece to build in auth/; this function's token-refresh path is
    what both will share once it exists."""
    settings = get_settings()
    creds_path = Path(settings.google_credentials_path)
    token_path = _token_path(user_id)

    if not creds_path.exists():
        raise AuthenticationError(
            f"Missing Google OAuth client file at {creds_path}",
            user_message="Google integrations aren't set up yet — missing OAuth client credentials.",
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise AuthenticationError(
                f"Failed to refresh Google token for {user_id}: {exc}",
                user_message="Your Google authorization expired and couldn't be refreshed. Please reconnect.",
            ) from exc
        token_path.write_text(creds.to_json())
        return creds

    if not run_local_server:
        raise AuthenticationError(
            f"No valid Google credentials for user {user_id}",
            user_message="Please connect your Google account first.",
        )

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError(
            f"Google OAuth flow failed for {user_id}: {exc}",
            user_message="Google authorization did not complete.",
        ) from exc

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    log.info("google_auth.authorized", extra={"user_id": user_id})
    return creds
