"""
Structured markers that tools embed in their text output so the UI can react
(play a video, open the camera) without relying on whatever the model
decides to say about the result.

Format: one line, `<PREFIX>` immediately followed by a JSON object. JSON (not
a `|`-delimited string) because real-world values contain delimiters — e.g.
YouTube titles like "Song | Artist | Label".

Parsing is line-based and tolerant of surrounding text on OTHER lines, which
matters because GuardrailMiddleware wraps untrusted tool output in
<untrusted_source> tags — the marker line survives intact inside the wrapper.
"""

from __future__ import annotations

import json

PLAY_MEDIA = "PLAY_MEDIA::"
REQUEST_CAMERA = "REQUEST_CAMERA::"


def build_marker(prefix: str, payload: dict) -> str:
    return prefix + json.dumps(payload, ensure_ascii=False)


def find_marker(content: str, prefix: str) -> dict | None:
    """Return the JSON payload of the first line starting with `prefix`, or
    None if absent or malformed. Never raises."""
    if not content or prefix not in content:
        return None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            try:
                data = json.loads(line[len(prefix):])
            except ValueError:
                return None
            return data if isinstance(data, dict) else None
    return None
