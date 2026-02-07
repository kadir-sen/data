"""Auth endpoints: register, login, Google OAuth, token refresh, me."""

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    exchange_google_code,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db import get_session
from app.models.user import User
from app.rbac import CurrentUser, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    auth_provider: str
    is_active: bool


# ── Register ────────────────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role="member",
        auth_provider="local",
    )
    session.add(user)
    await session.flush()

    await log_event(
        session,
        action="auth.register",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        detail=f"User registered: {body.email}",
    )
    await session.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── Login ───────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    await log_event(
        session,
        action="auth.login",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        detail=f"Login via password: {user.email}",
    )
    await session.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── Google OAuth ────────────────────────────────────────────────────
@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleLoginRequest, session: AsyncSession = Depends(get_session)):
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured",
        )

    google_info = await exchange_google_code(body.code)
    google_sub = google_info["sub"]
    email = google_info["email"]
    name = google_info.get("name", email)

    # Look up by google_sub first, then by email
    result = await session.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()

    if not user:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            # Link existing account
            user.google_sub = google_sub
            user.auth_provider = "google"
        else:
            # Create new user
            user = User(
                email=email,
                display_name=name,
                role="member",
                auth_provider="google",
                google_sub=google_sub,
            )
            session.add(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    await session.flush()
    await log_event(
        session,
        action="auth.login.google",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        detail=f"Login via Google: {email}",
    )
    await session.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── Refresh ─────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    user_id = uuid.UUID(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


# ── Me ──────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).where(User.id == uuid.UUID(current_user.id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
    )
