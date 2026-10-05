from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth, chat, conversations, documents, media, voice
from config.settings import get_settings
from core.agent import init_agent, shutdown_agent
from database.connection import check_connection, close_pool, execute_schema, init_pool
from database.models import SCHEMA_DDL
from utils.asyncio_compat import fix_windows_event_loop
from utils.logging import configure_logging, get_logger

fix_windows_event_loop()  # must run before uvicorn creates its event loop

log = get_logger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    pool = await init_pool()
    async with pool.connection() as conn:
        await execute_schema(conn, SCHEMA_DDL)
    log.info("startup.schema_ready")

    await init_agent()
    log.info("startup.agent_ready")

    yield

    await shutdown_agent()
    await close_pool()
    log.info("shutdown.complete")


app = FastAPI(title="AURA API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your actual frontend origin before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(voice.router)
app.include_router(media.router)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    db_ok = await check_connection()
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": db_ok,
        "config": settings.redacted_summary(),
    }
