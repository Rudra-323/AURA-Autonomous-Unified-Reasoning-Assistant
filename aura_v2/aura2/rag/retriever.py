"""
Hybrid retrieval: pgvector cosine similarity + Postgres full-text search,
combined via reciprocal rank fusion (RRF) — meaningfully better recall than
vector-only top-k, especially for exact terms (names, IDs, acronyms) that
embeddings alone often miss.

Every query filters by user_id FIRST (it's the leading column in the
WHERE clause and the composite access pattern the HNSW/GIN indexes are
built around) so one user's large document corpus never slows another
user's search — see database/models.py.
"""

from __future__ import annotations

from database.connection import get_connection
from rag.embeddings import embed_query
from utils.errors import DatabaseError
from utils.logging import get_logger

log = get_logger("rag.retriever")

_RRF_K = 60  # standard RRF constant; de-emphasizes rank differences beyond top results


async def hybrid_search(user_id: str, query: str, top_k: int = 5) -> list[dict]:
    query_embedding = await embed_query(query)

    sql = """
    WITH vector_ranked AS (
        SELECT chunk_id, content, document_id,
               row_number() OVER (ORDER BY embedding <=> %(qvec)s) AS rank
        FROM document_chunks
        WHERE user_id = %(user_id)s
        ORDER BY embedding <=> %(qvec)s
        LIMIT 25
    ),
    keyword_ranked AS (
        SELECT chunk_id, content, document_id,
               row_number() OVER (ORDER BY ts_rank(to_tsvector('english', content), plainto_tsquery('english', %(query)s)) DESC) AS rank
        FROM document_chunks
        WHERE user_id = %(user_id)s
          AND to_tsvector('english', content) @@ plainto_tsquery('english', %(query)s)
        LIMIT 25
    )
    SELECT
        COALESCE(v.chunk_id, k.chunk_id) AS chunk_id,
        COALESCE(v.content, k.content) AS content,
        COALESCE(v.document_id, k.document_id) AS document_id,
        (COALESCE(1.0 / (%(rrf_k)s + v.rank), 0) + COALESCE(1.0 / (%(rrf_k)s + k.rank), 0)) AS score
    FROM vector_ranked v
    FULL OUTER JOIN keyword_ranked k ON v.chunk_id = k.chunk_id
    ORDER BY score DESC
    LIMIT %(top_k)s
    """

    try:
        async with get_connection() as conn:
            rows = await (await conn.execute(sql, {
                "qvec": str(query_embedding), "user_id": user_id, "query": query,
                "rrf_k": _RRF_K, "top_k": top_k,
            })).fetchall()
    except Exception as exc:  # noqa: BLE001
        raise DatabaseError(f"Hybrid search failed: {exc}") from exc

    return [{"chunk_id": r["chunk_id"], "content": r["content"], "document_id": r["document_id"],
             "score": float(r["score"])} for r in rows]
