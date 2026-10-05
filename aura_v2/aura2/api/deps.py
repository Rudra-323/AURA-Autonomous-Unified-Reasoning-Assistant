from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.service import decode_access_token
from utils.errors import AuthenticationError

_bearer = HTTPBearer()


async def get_current_user_id(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    try:
        return decode_access_token(creds.credentials)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.user_message) from exc
