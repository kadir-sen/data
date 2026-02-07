"""API routers — one per domain resource."""

from app.routers import (
    audit, auth, connectors, effort, health, metrics,
    observability, reports, sprints, work_items,
)

__all__ = [
    "audit",
    "auth",
    "connectors",
    "effort",
    "health",
    "metrics",
    "observability",
    "reports",
    "sprints",
    "work_items",
]
