"""
Web search tool — async httpx directly against the Google Custom Search
JSON API (Programmable Search Engine).

Replaces an earlier Tavily-based tool: one Google Cloud project now covers
both this and YouTube, instead of managing two separate API providers.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from config.settings import get_settings
from utils.errors import ExternalServiceError
from utils.logging import get_logger
from utils.security import describe_http_error

log = get_logger("tools.web_search")

_TIMEOUT = 10.0
_MAX_RESULTS = 5


async def run_google_search(query: str, max_results: int = _MAX_RESULTS) -> list[dict]:
    settings = get_settings()
    if not (settings.google_api_key and settings.google_search_cx):
        raise ExternalServiceError(
            "Google Search is not configured (missing GOOGLE_API_KEY/GOOGLE_SEARCH_CX)"
        )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.google_api_key,
                    "cx": settings.google_search_cx,
                    "q": query,
                    "num": min(max(max_results, 1), 10),
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise ExternalServiceError(f"Google Search failed ({describe_http_error(exc)})") from exc

    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in data.get("items", [])
    ]


@tool
async def google_search(query: str) -> str:
    """Search the web (via Google) for current information, news, or facts
    you're not confident about from memory alone. Say when information came
    from a search versus your own general knowledge."""
    try:
        results = await run_google_search(query)
    except ExternalServiceError as exc:
        log.warning("google_search.failed", extra={"query": query, "error": str(exc)})
        return f"Web search failed: {exc.user_message}"
    if not results:
        return "No results found."
    return "\n".join(f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results)
