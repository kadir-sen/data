"""Role-Based Access Control – JWT-validated, permission-gated dependencies.

Roles: admin, manager, member.

Permission matrix
─────────────────
admin   → "*" (all permissions)
manager → cases:*, connectors:read, team:dashboard, team:manage
member  → cases:read, connectors:read (own), dashboard:own, effort:own
"""

from enum import StrEnum
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.auth import decode_token
from app.config import settings  # noqa: F401 – used indirectly via decode_token


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class CurrentUser(BaseModel):
    id: str
    email: str
    role: Role


# ── Permission map ──────────────────────────────────────────────────
PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {"*"},
    Role.MANAGER: {
        "cases:read", "cases:write", "cases:assign",
        "connectors:read", "connectors:write",
        "team:dashboard", "team:manage",
        "effort:read", "effort:write", "effort:read_team",
    },
    Role.MEMBER: {
        "cases:read",
        "connectors:read",
        "dashboard:own", "effort:own",
        "effort:read", "effort:write",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    allowed = PERMISSIONS.get(role, set())
    return "*" in allowed or permission in allowed


# ── JWT dependency ──────────────────────────────────────────────────
async def get_current_user(request: Request) -> CurrentUser:
    """Extract and validate the JWT Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    return CurrentUser(
        id=payload["sub"],
        email=payload.get("email", ""),
        role=Role(payload["role"]),
    )


def require_permission(permission: str):
    """Dependency factory — use as `Depends(require_permission("cases:write"))`."""

    async def _check(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user

    return _check


def require_role(*roles: Role):
    """Dependency factory — use as `Depends(require_role(Role.ADMIN))`."""

    async def _check(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {user.role} not allowed; requires one of {[r.value for r in roles]}",
            )
        return user

    return _check
