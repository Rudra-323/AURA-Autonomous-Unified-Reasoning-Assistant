"""
Agent construction — async throughout. Built once per process; MCP tools
(if any servers are configured) are fetched once at startup and merged with
AURA's own tool registry.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from config.settings import get_settings
from core.context import AgentContext
from core.middleware import build_middleware_stack
from core.prompts import build_system_prompt
from mcp.servers import get_mcp_server_config
from tools.registry import get_tools
from utils.logging import get_logger

log = get_logger("core.agent")

_agent = None
_checkpointer_cm = None


def _build_chat_model(model_name: str) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model_name,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={"X-Title": "AURA"},
    )


async def _load_mcp_tools() -> list:
    server_config = get_mcp_server_config()
    if not server_config:
        return []
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient(server_config)
        mcp_tools = await client.get_tools()
        log.info("agent.mcp_tools_loaded", extra={"count": len(mcp_tools)})
        return mcp_tools
    except Exception as exc:  # noqa: BLE001 — MCP is optional, never fatal
        log.warning("agent.mcp_tools_failed", extra={"error": str(exc)})
        return []


async def init_agent():
    """Call once at FastAPI startup. Opens the async checkpointer connection
    and builds the compiled agent graph."""
    global _agent, _checkpointer_cm
    settings = get_settings()

    _checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.postgres_uri)
    checkpointer = await _checkpointer_cm.__aenter__()
    await checkpointer.setup()

    primary_model = _build_chat_model(settings.openrouter_model)
    fallback_model = _build_chat_model(settings.openrouter_fallback_model)

    all_tools = get_tools() + await _load_mcp_tools()

    _agent = create_agent(
        model=primary_model,
        tools=all_tools,
        system_prompt=build_system_prompt(),
        middleware=build_middleware_stack(primary_model=primary_model, fallback_model=fallback_model),
        checkpointer=checkpointer,
        context_schema=AgentContext,
    )
    log.info("agent.built", extra={"tool_count": len(all_tools)})
    return _agent


async def shutdown_agent() -> None:
    global _checkpointer_cm
    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)
        _checkpointer_cm = None


def get_agent():
    if _agent is None:
        raise RuntimeError("Agent not initialized — call init_agent() at startup first.")
    return _agent
