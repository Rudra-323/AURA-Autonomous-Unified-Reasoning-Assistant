"""
Application-owned schema. LangGraph's own checkpoint tables are separate —
created by AsyncPostgresSaver.setup(), never touched here (see core/agent.py
/ scripts/init_db.py).
"""

from __future__ import annotations

SCHEMA_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    thread_id       TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL DEFAULT 'New Chat',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS memory_records (
    memory_id       BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category        TEXT NOT NULL CHECK (category IN ('FACT','PREFERENCE','PROFILE','TASK','CONTEXT','TEMPORARY')),
    content         TEXT NOT NULL,
    embedding       vector(768),
    source_conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_memory_user_category ON memory_records (user_id, category);

-- Uploaded documents for RAG. content_hash dedupes re-uploads of the same file.
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, content_hash)
);

-- Ingestion job status, polled/pushed to the UI so upload never blocks the request.
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id          TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
    chunks_total    INTEGER,
    chunks_done     INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chunks become queryable incrementally as they're embedded, not all-or-nothing.
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id        BIGSERIAL PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(768),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON document_chunks (user_id);
-- Approximate nearest-neighbor index; filter by user_id first via the composite
-- pattern in queries so one user's large corpus never slows another's search.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
-- Keyword search complements vector search for hybrid retrieval.
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts ON document_chunks
    USING gin (to_tsvector('english', content));

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    conversation_id TEXT,
    action          TEXT NOT NULL,
    tool_name       TEXT,
    success         BOOLEAN NOT NULL,
    detail          TEXT,
    tokens_used     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_user_created ON audit_events (user_id, created_at DESC);
"""
