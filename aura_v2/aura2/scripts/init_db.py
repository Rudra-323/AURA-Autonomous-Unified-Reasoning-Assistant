"""
Run once before first use:  python -m scripts.init_db
(FastAPI's lifespan also applies the idempotent app schema on every
startup — see api/main.py — but the checkpointer's own tables need this
explicit step run once, since AsyncPostgresSaver.setup() isn't in the
request-serving path.)
"""

from __future__ import annotations

import asyncio

from config.settings import get_settings
from database.connection import close_pool, execute_schema, get_connection, init_pool
from database.models import SCHEMA_DDL
from utils.asyncio_compat import fix_windows_event_loop
from utils.logging import configure_logging, get_logger

fix_windows_event_loop()  # must run before asyncio.run() below

log = get_logger("scripts.init_db")


async def init_application_schema() -> None:
    await init_pool()
    async with get_connection() as conn:
        await execute_schema(conn, SCHEMA_DDL)
    log.info("init_db.application_schema_ready")


async def init_checkpointer_schema() -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    settings = get_settings()
    async with AsyncPostgresSaver.from_conn_string(settings.postgres_uri) as saver:
        await saver.setup()
    log.info("init_db.checkpointer_schema_ready")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    print("Initializing AURA application schema (users, conversations, memory, documents, RAG, audit)...")
    await init_application_schema()
    print("Initializing LangGraph checkpoint schema...")
    await init_checkpointer_schema()
    await close_pool()
    print("Database initialization complete.")


if __name__ == "__main__":
    asyncio.run(main())
