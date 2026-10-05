"""
MCP server registry. Tools from these servers are merged with AURA's own
hand-written tools (tools/registry.py) at agent build time via
langchain-mcp-adapters — no custom integration code needed per server.

Empty/commented entries are intentionally left for the user to fill in with
real server commands/URLs (e.g. `npx -y @notionhq/notion-mcp-server`) since
these require their own API keys and setup outside this codebase.
"""

from __future__ import annotations

from config.settings import get_settings


def get_mcp_server_config() -> dict:
    """Returns the connections dict for MultiServerMCPClient. Empty by
    default — MCP is additive and optional; the agent works fully without
    any server configured here."""
    settings = get_settings()
    servers: dict = {}

    # Example (uncomment and configure once you have the server + API key):
    # servers["notion"] = {
    #     "command": "npx",
    #     "args": ["-y", "@notionhq/notion-mcp-server"],
    #     "transport": "stdio",
    #     "env": {"NOTION_API_KEY": settings.notion_api_key},
    # }
    # servers["github"] = {
    #     "url": "https://api.githubcopilot.com/mcp/",
    #     "transport": "http",
    #     "headers": {"Authorization": f"Bearer {settings.github_token}"},
    # }

    return servers
