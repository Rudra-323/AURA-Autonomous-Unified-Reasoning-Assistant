"""
Cross-cutting security helpers.

The prompt-injection heuristic here is deliberately narrow: it flags
retrieved content (search results, email bodies, uploaded documents) that
contains obvious instruction-like phrasing, so GuardrailMiddleware can wrap
it with a clear "this is untrusted data" marker before it reaches the model.
This is a defense-in-depth measure, NOT the actual security boundary — the
real boundary is that consequential tools always require human approval
regardless of what triggered the call (see core/middleware.py). A heuristic
can be evaded; the approval gate cannot.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^([^@]{1,3})[^@]*(@.+)$")

# Narrow, high-precision patterns only — false positives on legitimate
# content (e.g. a doc that says "ignore the footnote") are cheap; false
# negatives on real injection attempts are the actual risk, so keep this
# list reviewed and short rather than trying to be exhaustive.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.I),
    re.compile(r"disregard (all |any )?(previous|prior|above)", re.I),
    re.compile(r"you are now (in )?(developer|admin|system) mode", re.I),
    re.compile(r"new instructions?:", re.I),
    re.compile(r"forward (all |any )?(emails?|messages?) to", re.I),
]


def mask_email(address: str) -> str:
    match = _EMAIL_RE.match(address.strip())
    if not match:
        return "***"
    return f"{match.group(1)}***{match.group(2)}"


def truncate_for_log(text: str, max_len: int = 200) -> str:
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated, {len(text)} chars total]"


def looks_like_injection(text: str) -> bool:
    """Heuristic only — used to wrap/flag untrusted content, never to block
    outright (a false positive blocking a legitimate document is worse than
    a flagged-but-passed-through one, given the approval gate downstream)."""
    if not text:
        return False
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def wrap_untrusted(source_label: str, content: str) -> str:
    """Wrap retrieved/external content so the model sees it clearly marked
    as data, not instructions. Used for search results, email bodies, and
    RAG-retrieved document chunks before they're inserted into context."""
    flag = " [flagged: instruction-like phrasing detected]" if looks_like_injection(content) else ""
    return (
        f"<untrusted_source name=\"{source_label}\"{flag}>\n{content}\n</untrusted_source>"
    )


def describe_http_error(exc: Exception) -> str:
    """Short, safe description of an httpx error — status code or exception
    class only. NEVER use str(exc) for httpx errors in user-/model-visible
    text or logs: httpx embeds the full request URL, and several APIs we call
    (Google Search, YouTube, OpenWeatherMap) carry the API key in the query
    string, so str(exc) leaks the key."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return f"HTTP {status}"
    return type(exc).__name__
