"""
Auth service. Passwords hashed with bcrypt (called directly, not via
passlib — see note below), sessions as JWTs. This is deliberately simple
(no refresh-token rotation, no OAuth-as-login) — enough to make per-user
isolation real and demoable, not a full auth system. Swap for a real
provider (Auth0/Clerk/Supabase Auth) before any real deployment beyond a
portfolio demo.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from config.settings import get_settings
from database.connection import get_connection
from utils.errors import AuthenticationError, DatabaseError
from utils.logging import get_logger

log = get_logger("auth.service")

# Calling bcrypt directly rather than through passlib's CryptContext: newer
# bcrypt releases (4.1+) dropped an internal module passlib's version-sniffing
# code depends on, which makes passlib misreport a spurious "password too
# long" error for perfectly normal, short passwords. bcrypt's own API is
# simple enough not to need passlib's wrapper anyway.
_BCRYPT_MAX_BYTES = 72  # bcrypt's real, hard limit — worth enforcing explicitly


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > _BCRYPT_MAX_BYTES:
        raise AuthenticationError(
            "Password too long", user_message=f"Password must be at most {_BCRYPT_MAX_BYTES} bytes."
        )
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


async def create_user(email: str, password: str, display_name: str | None = None) -> str:
    user_id = str(uuid.uuid4())
    try:
        async with get_connection() as conn:
            cur = await conn.execute(
                """INSERT INTO users (user_id, email, hashed_password, display_name)
                   VALUES (%(id)s, %(email)s, %(pw)s, %(name)s)
                   ON CONFLICT (email) DO NOTHING RETURNING user_id""",
                {"id": user_id, "email": email.lower().strip(), "pw": hash_password(password), "name": display_name},
            )
            row = await cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        raise DatabaseError(f"Failed to create user: {exc}") from exc

    if row is None:
        raise AuthenticationError("Email already registered", user_message="An account with that email already exists.")
    return row["user_id"]


async def authenticate(email: str, password: str) -> str:
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT user_id, hashed_password FROM users WHERE email = %(email)s",
            {"email": email.lower().strip()},
        )
        row = await cur.fetchone()

    if row is None or not verify_password(password, row["hashed_password"]):
        raise AuthenticationError("Invalid credentials", user_message="Incorrect email or password.")
    return row["user_id"]


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthenticationError(f"Invalid token: {exc}", user_message="Your session has expired — please log in again.") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing subject", user_message="Invalid session — please log in again.")
    return user_id
