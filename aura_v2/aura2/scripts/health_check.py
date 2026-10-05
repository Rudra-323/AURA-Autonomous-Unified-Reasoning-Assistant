"""Run: python -m scripts.health_check"""

from __future__ import annotations

import asyncio
import sys

from config.settings import get_settings
from database.connection import check_connection, close_pool
from utils.errors import ConfigurationError


async def main() -> int:
    print("AURA Health Check\n")
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(f"Configuration: FAILED — {exc.user_message}")
        return 1

    summary = settings.redacted_summary()
    print(f"Configuration: OK ({summary['app_env']})")

    db_ok = await check_connection()
    print(f"PostgreSQL: {'OK' if db_ok else 'FAILED'}")
    print(f"LLM configuration: OK (primary={summary['openrouter_model']})")
    print(f"Tavily: {'CONFIGURED' if summary['tavily_configured'] else 'NOT CONFIGURED'}")
    print(f"Google (Search/YouTube): {'CONFIGURED' if summary['google_configured'] else 'NOT CONFIGURED'}")
    print(f"Google OAuth (Gmail/Calendar/Drive): {'CONFIGURED' if summary['google_credentials_configured'] else 'NOT CONFIGURED'}")
    print(f"Voice enabled: {summary['voice_enabled']}")
    print(f"Redis configured: {summary['redis_configured']}")
    print(f"LangSmith tracing: {'ON' if summary['langsmith_tracing'] else 'OFF'}")

    await close_pool()
    healthy = db_ok
    print(f"\nOverall: {'HEALTHY' if healthy else 'UNHEALTHY'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
