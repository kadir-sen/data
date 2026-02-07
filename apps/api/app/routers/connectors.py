"""Connectors endpoints – manage source tokens (Jira, GitLab, Slack, Notion, Google).

Background jobs use the service-account token when one is configured for the
source; otherwise they fall back to the requesting user's personal token.
The `resolve_token_for_source()` helper encapsulates this logic.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.crypto import decrypt, encrypt
from app.db import get_session
from app.models.source_token import SourceToken
from app.rbac import CurrentUser, Role, get_current_user, require_permission

router = APIRouter(prefix="/connectors", tags=["connectors"])

VALID_SOURCES = {"jira", "gitlab", "slack", "notion", "google"}


# ── Schemas ─────────────────────────────────────────────────────────
class ConnectorCreateRequest(BaseModel):
    source: str
    token: str
    label: str = ""
    scopes: str | None = None
    is_service_account: bool = False


class ConnectorResponse(BaseModel):
    id: str
    source: str
    label: str
    scopes: str | None
    is_service_account: bool
    created_at: str
    updated_at: str


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorResponse]


# ── Helpers ─────────────────────────────────────────────────────────
def _to_response(tok: SourceToken) -> ConnectorResponse:
    return ConnectorResponse(
        id=str(tok.id),
        source=tok.source,
        label=tok.label,
        scopes=tok.scopes,
        is_service_account=tok.is_service_account,
        created_at=tok.created_at.isoformat(),
        updated_at=tok.updated_at.isoformat(),
    )


# ── List connectors (own tokens; admin sees all) ───────────────────
@router.get("", response_model=ConnectorListResponse)
async def list_connectors(
    user: CurrentUser = Depends(require_permission("connectors:read")),
    session: AsyncSession = Depends(get_session),
):
    uid = uuid.UUID(user.id)
    if user.role == Role.ADMIN:
        result = await session.execute(select(SourceToken).order_by(SourceToken.created_at.desc()))
    else:
        result = await session.execute(
            select(SourceToken)
            .where(SourceToken.user_id == uid)
            .order_by(SourceToken.created_at.desc())
        )
    tokens = result.scalars().all()
    return ConnectorListResponse(connectors=[_to_response(t) for t in tokens])


# ── Create (connect a source) ──────────────────────────────────────
@router.post("", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    body: ConnectorCreateRequest,
    user: CurrentUser = Depends(require_permission("connectors:read")),
    session: AsyncSession = Depends(get_session),
):
    if body.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source. Must be one of: {', '.join(sorted(VALID_SOURCES))}",
        )
    # Only admin can create service-account tokens
    if body.is_service_account and user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create service-account tokens",
        )

    uid = uuid.UUID(user.id)
    token_obj = SourceToken(
        user_id=uid,
        source=body.source,
        label=body.label,
        encrypted_token=encrypt(body.token),
        scopes=body.scopes,
        is_service_account=body.is_service_account,
    )
    session.add(token_obj)
    await session.flush()

    await log_event(
        session,
        action="token.created",
        actor_id=uid,
        resource_type="source_token",
        resource_id=str(token_obj.id),
        detail=f"Connected {body.source}" + (" (service account)" if body.is_service_account else ""),
        meta={"source": body.source, "scopes": body.scopes},
    )
    await session.commit()
    await session.refresh(token_obj)
    return _to_response(token_obj)


# ── Delete (disconnect a source) ───────────────────────────────────
@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: uuid.UUID,
    user: CurrentUser = Depends(require_permission("connectors:read")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SourceToken).where(SourceToken.id == connector_id))
    token_obj = result.scalar_one_or_none()
    if not token_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    uid = uuid.UUID(user.id)
    # Members can only delete their own tokens
    if user.role != Role.ADMIN and token_obj.user_id != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your connector")

    await log_event(
        session,
        action="token.deleted",
        actor_id=uid,
        resource_type="source_token",
        resource_id=str(token_obj.id),
        detail=f"Disconnected {token_obj.source}",
    )
    await session.delete(token_obj)
    await session.commit()


# ── Resolve token for background jobs ──────────────────────────────
async def resolve_token_for_source(
    source: str,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> str:
    """Return the decrypted token for a source.

    Strategy:
      1. If a service-account token exists for this source, use it.
      2. Otherwise fall back to the user's personal token.
    Raises ValueError if no token is found.
    """
    # Try service account first
    result = await session.execute(
        select(SourceToken).where(
            SourceToken.source == source,
            SourceToken.is_service_account.is_(True),
        ).limit(1)
    )
    token_obj = result.scalar_one_or_none()

    if not token_obj:
        # Fall back to user's personal token
        result = await session.execute(
            select(SourceToken).where(
                SourceToken.source == source,
                SourceToken.user_id == user_id,
            ).limit(1)
        )
        token_obj = result.scalar_one_or_none()

    if not token_obj:
        raise ValueError(f"No token found for source={source}, user={user_id}")

    # Audit the usage
    await log_event(
        session,
        action="token.used",
        actor_id=user_id,
        resource_type="source_token",
        resource_id=str(token_obj.id),
        detail=f"Token resolved for {source}" + (" (service account)" if token_obj.is_service_account else ""),
        meta={"source": source, "is_service_account": token_obj.is_service_account},
    )

    return decrypt(token_obj.encrypted_token)
