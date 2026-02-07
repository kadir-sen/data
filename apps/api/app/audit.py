"""Thin helper for writing audit log entries from any module."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_event(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: str | None = None,
    meta: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        meta=meta,
    )
    session.add(entry)
    await session.flush()
    return entry
