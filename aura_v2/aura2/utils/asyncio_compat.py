"""
Windows-specific asyncio fix.

Windows' default event loop (ProactorEventLoop) is incompatible with
psycopg's async networking, which needs SelectorEventLoop instead. This has
no effect on Linux/Mac (they don't have this split at all) — safe to call
unconditionally from every async entrypoint (scripts, api/main.py).

Must be called BEFORE any asyncio.run()/uvicorn startup — it only changes
what future event loops get constructed, not any loop already running.
"""

from __future__ import annotations

import asyncio
import sys


def fix_windows_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
