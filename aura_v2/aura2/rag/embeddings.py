"""
Embedding generation via sentence-transformers, loaded once as a process
singleton (loading the model per-call would be a real latency problem).
`intfloat/multilingual-e5-base` is the default — it covers English, Hindi,
and Odia reasonably (unlike most English-only embedding models), which
matters since AURA's voice/documents aren't English-only.

Runs on CPU by default; sentence-transformers picks up CUDA automatically
if available. Wrapped in asyncio.to_thread so it never blocks the event
loop in the async ingestion pipeline.
"""

from __future__ import annotations

import asyncio
import hashlib

from config.settings import get_settings
from utils.logging import get_logger

log = get_logger("rag.embeddings")

_model = None

# e5 models expect a "query: " / "passage: " prefix convention for best
# retrieval quality — skipping this measurably hurts recall with e5 models.
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        settings = get_settings()
        log.info("embeddings.loading_model", extra={"model": settings.embedding_model})
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _embed_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


async def embed_passages(texts: list[str]) -> list[list[float]]:
    """Batch-embed document chunks. Always batch (one call for many chunks)
    rather than one call per chunk — this is the single biggest lever on
    ingestion latency/cost for large documents."""
    prefixed = [_PASSAGE_PREFIX + t for t in texts]
    return await asyncio.to_thread(_embed_sync, prefixed)


async def embed_query(text: str) -> list[float]:
    result = await asyncio.to_thread(_embed_sync, [_QUERY_PREFIX + text])
    return result[0]


def content_hash(raw_bytes: bytes) -> str:
    """Used to dedupe re-uploads of the same file — skip reprocessing
    entirely if a user uploads a document they already uploaded."""
    return hashlib.sha256(raw_bytes).hexdigest()
