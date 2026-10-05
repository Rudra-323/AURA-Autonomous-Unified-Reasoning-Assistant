"""
Connects a user's Gmail/Calendar/Drive access via an interactive browser
OAuth consent flow, and saves the resulting token under their user_id.

This exists because the app itself has no in-browser "Connect Google
Account" flow yet (that needs a proper OAuth redirect + callback pair of
API endpoints — a real but not-yet-built piece, noted in the README's
Known Limitations). This script is the honest, working stand-in for local
development: run it once per user, a browser window opens for you to sign
in and approve, and after that Gmail/Calendar/Drive tools work for that
account without needing this script again (until the token expires and
can't silently refresh).

Usage:
    python -m scripts.connect_gmail your@email.com
"""

from __future__ import annotations

import asyncio
import sys

from database.connection import close_pool, get_connection, init_pool
from services.google_auth import get_google_credentials
from utils.asyncio_compat import fix_windows_event_loop
from utils.errors import AuraError

fix_windows_event_loop()


async def _find_user_id(email: str) -> str | None:
    await init_pool()
    try:
        async with get_connection() as conn:
            row = await (await conn.execute(
                "SELECT user_id FROM users WHERE email = %(email)s", {"email": email.lower().strip()}
            )).fetchone()
        return row["user_id"] if row else None
    finally:
        await close_pool()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.connect_gmail your@email.com")
        return 1
    email = sys.argv[1]

    user_id = asyncio.run(_find_user_id(email))
    if not user_id:
        print(f"No account found for {email} — sign up in the app first, then run this again.")
        return 1

    print(f"Opening a browser window for {email} to sign in and approve access...")
    print("(Gmail read/compose/send, Calendar events, and Drive per-file access)")
    try:
        get_google_credentials(user_id, run_local_server=True)
    except AuraError as exc:
        print(f"Failed: {exc.user_message}")
        return 1

    print(f"\nDone — Gmail/Calendar/Drive tools now work for {email} in the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
