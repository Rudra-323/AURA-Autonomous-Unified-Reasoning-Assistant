"""Simple recursive character chunker. Splits on paragraph -> line ->
sentence -> word boundaries, falling back progressively, with overlap so
context isn't lost at chunk edges."""

from __future__ import annotations

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    def split(t: str, seps: list[str]) -> list[str]:
        if not seps:
            return [t]
        sep = seps[0]
        if sep == "":
            return [t[i:i + chunk_size] for i in range(0, len(t), chunk_size)]
        parts = t.split(sep)
        return [p for p in parts if p]

    pieces: list[str] = []
    for sep_index in range(len(_SEPARATORS)):
        pieces = split(text, [_SEPARATORS[sep_index]])
        if all(len(p) <= chunk_size for p in pieces) or sep_index == len(_SEPARATORS) - 1:
            break

    # Merge small pieces back up to ~chunk_size, with overlap carried forward.
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = (current + " " + piece).strip() if current else piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = (current[-overlap:] + " " + piece).strip() if overlap and current else piece
    if current:
        chunks.append(current)
    return chunks
