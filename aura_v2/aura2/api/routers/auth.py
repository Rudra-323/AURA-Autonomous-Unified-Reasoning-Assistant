from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from auth.service import authenticate, create_access_token, create_user
from utils.errors import AuraError

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=TokenResponse)
async def signup(body: SignupRequest) -> TokenResponse:
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    try:
        user_id = await create_user(body.email, body.password, body.display_name)
    except AuraError as exc:
        raise HTTPException(status_code=400, detail=exc.user_message) from exc
    return TokenResponse(access_token=create_access_token(user_id))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    try:
        user_id = await authenticate(body.email, body.password)
    except AuraError as exc:
        raise HTTPException(status_code=401, detail=exc.user_message) from exc
    return TokenResponse(access_token=create_access_token(user_id))
