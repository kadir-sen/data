"""Audit log endpoint – read-only access for admins."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.audit_log import AuditLog
from app.rbac import CurrentUser, Role, require_role

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntry(BaseModel):
    id: str
    actor_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    detail: str | None
    meta: dict | None
    created_at: str


class AuditListResponse(BaseModel):
    entries: list[AuditEntry]
    total: int


@router.get("", response_model=AuditListResponse)
async def list_audit_logs(
    _user: CurrentUser = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
    action: str | None = Query(None, description="Filter by action, e.g. token.created"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.where(AuditLog.action == action)

    # Total count (unoptimized for now; add count query for large datasets)
    all_result = await session.execute(query)
    total = len(all_result.scalars().all())

    # Paginated result
    result = await session.execute(query.offset(offset).limit(limit))
    entries = result.scalars().all()

    return AuditListResponse(
        entries=[
            AuditEntry(
                id=str(e.id),
                actor_id=str(e.actor_id) if e.actor_id else None,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                detail=e.detail,
                meta=e.meta,
                created_at=e.created_at.isoformat(),
            )
            for e in entries
        ],
        total=total,
    )
