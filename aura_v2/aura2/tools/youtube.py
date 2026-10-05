"""
YouTube tool. A backend tool cannot play audio itself — it finds the best
matching video via the YouTube Data API and returns a structured result
(video_id + embed URL) that the UI renders as a playable embedded player.
This mirrors how real voice assistants work: the assistant resolves
"what to play," the client device is what actually plays it.
"""

from __future__ import annotations

import html

import httpx
from langchain_core.tools import tool

from config.settings import get_settings
from utils.logging import get_logger
from utils.media_markers import PLAY_MEDIA, build_marker
from utils.security import describe_http_error

log = get_logger("tools.youtube")

_TIMEOUT = 8.0
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


@tool
async def youtube_search_and_play(query: str) -> str:
    """Search YouTube for a video/song and prepare it for playback, e.g.
    "play a heart-touching Arijit Singh song" or "play the trailer for X".
    Returns the video title and an embeddable URL — the UI plays it.

    Args:
        query: What to search for and play, in the user's own words.
    """
    settings = get_settings()
    if not settings.google_api_key:
        return "YouTube search isn't configured (missing GOOGLE_API_KEY)."

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                _SEARCH_URL,
                params={
                    "key": settings.google_api_key,
                    "q": query,
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 1,
                    "videoEmbeddable": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        log.warning("youtube.search_failed", extra={"query": query, "status": status})
        if status in (400, 403):
            return (
                "YouTube rejected the request — check that the YouTube Data API v3 is "
                "enabled for your GOOGLE_API_KEY and that its quota isn't exhausted."
            )
        return f"YouTube search failed (HTTP {status})."
    except httpx.HTTPError as exc:
        # Never put str(exc) in output or logs: httpx includes the request URL,
        # which contains the API key. Return a string rather than raising — an
        # exception out of a @tool function can kill the whole streamed reply.
        log.warning("youtube.search_failed", extra={"query": query, "error": describe_http_error(exc)})
        return "YouTube search failed because of a network problem — please try again."

    items = data.get("items", [])
    if not items:
        return f"Couldn't find a video matching '{query}'."

    try:
        video = items[0]
        video_id = video["id"]["videoId"]
        # The YouTube API returns HTML-escaped titles (e.g. "&amp;", "&#39;").
        title = html.unescape(video["snippet"]["title"])
    except (KeyError, TypeError, IndexError) as exc:
        log.warning("youtube.unexpected_response", extra={"error": str(exc)})
        return "YouTube returned an unexpected response — please try again."

    embed_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
    log.info("youtube.playing", extra={"video_id": video_id})

    # JSON marker on its own line: the API layer (services/agent_service.py)
    # reads it straight off the tool message to trigger playback in the UI.
    marker = build_marker(PLAY_MEDIA, {"video_id": video_id, "title": title, "embed_url": embed_url})
    return f"{marker}\nNow playing: {title}"
