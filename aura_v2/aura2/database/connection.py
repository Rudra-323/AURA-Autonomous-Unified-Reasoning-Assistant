"""
Async PostgreSQL access via a shared connection pool (psycopg3 + psycopg_pool).
Replaces v1's per-request `psycopg.connect()` — a pool is required once
multiple async requests can be in flight concurrently, which is the whole
point of moving to FastAPI/async in the first place.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from config.settings import get_settings
from utils.asyncio_compat import fix_windows_event_loop
from utils.errors import DatabaseError
from utils.logging import get_logger

fix_windows_event_loop()  # must run before any event loop is created

log = get_logger("database.connection")

_pool: AsyncConnectionPool | None = None


async def init_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    _pool = AsyncConnectionPool(
        conninfo=settings.postgres_uri,
        max_size=20,
        kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    # wait=True (with an explicit timeout) so a bad POSTGRES_URI or an
    # unreachable database fails loudly, right here, with one clear error —
    # not as an endless stream of "error connecting in 'pool-1':" background
    # retry spam from a pool that opened "successfully" but can't actually
    # reach anything.
    await _pool.open(wait=True, timeout=30)
    log.info("database.pool_opened")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("database.pool_closed")


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    pool = await init_pool()
    try:
        async with pool.connection() as conn:
            yield conn
    except psycopg.OperationalError as exc:
        raise DatabaseError(
            f"Could not reach PostgreSQL: {exc}",
            user_message="I couldn't reach the database right now.",
        ) from exc


async def check_connection() -> bool:
    try:
        async with get_connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except DatabaseError:
        return False


async def execute_schema(conn: psycopg.AsyncConnection, ddl: str) -> None:
    """Run a multi-statement DDL string one statement at a time. psycopg3's
    async mode (unlike psycopg2) refuses multiple SQL commands in a single
    .execute() call — this is the one place that needs to know that, so
    every other caller can just pass a normal semicolon-separated schema
    string without thinking about it.

    Comment-only lines (`-- ...`) are stripped before splitting on `;` —
    a comment is allowed to contain a semicolon (e.g. "index X; filter by Y")
    without that being mistaken for a statement boundary."""
    code_only = "\n".join(
        line for line in ddl.splitlines() if not line.strip().startswith("--")
    )
    for statement in code_only.split(";"):
        statement = statement.strip()
        if statement:
            await conn.execute(statement)
