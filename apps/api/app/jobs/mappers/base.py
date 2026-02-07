"""Base mapper abstraction for raw_event -> canonical tables."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MapperResult:
    """Holds the normalized entities produced from a single raw_event."""

    persons: list[dict[str, Any]] = field(default_factory=list)
    sprints: list[dict[str, Any]] = field(default_factory=list)
    work_items: list[dict[str, Any]] = field(default_factory=list)
    doc_entries: list[dict[str, Any]] = field(default_factory=list)
    interaction_events: list[dict[str, Any]] = field(default_factory=list)
    external_links: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def entity_count(self) -> int:
        return (
            len(self.persons)
            + len(self.sprints)
            + len(self.work_items)
            + len(self.doc_entries)
            + len(self.interaction_events)
        )


class BaseMapper(ABC):
    """Abstract base class for source-specific mappers.

    Each mapper knows how to extract canonical entities from a raw_event
    payload for its specific source system.
    """

    source: str  # e.g. "jira", "gitlab", "notion"

    @abstractmethod
    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        """Transform a raw_event payload into normalized canonical entities.

        Args:
            entity_type: The type of entity (issue, sprint, page, message, etc.)
            entity_id: The source-native ID of the entity.
            payload: The full raw_event JSONB payload.

        Returns:
            MapperResult with all extracted canonical entities.
        """

    # ── helpers shared across mappers ──────────────────────────────────

    @staticmethod
    def _safe_get(d: dict, *keys: str, default: Any = None) -> Any:
        """Nested dict lookup with safe fallback."""
        current = d
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current

    @staticmethod
    def _normalize_priority(raw: str | None) -> str | None:
        """Normalize priority strings across systems to canonical values."""
        if not raw:
            return None
        lower = raw.lower().strip()
        mapping = {
            # Jira priorities
            "highest": "critical",
            "blocker": "critical",
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "normal": "medium",
            "low": "low",
            "lowest": "low",
            "trivial": "low",
            # GitLab labels
            "priority::critical": "critical",
            "priority::high": "high",
            "priority::medium": "medium",
            "priority::low": "low",
            # Notion select values
            "urgent": "critical",
            "p0": "critical",
            "p1": "high",
            "p2": "medium",
            "p3": "low",
        }
        return mapping.get(lower, lower if lower in ("critical", "high", "medium", "low") else None)

    @staticmethod
    def _normalize_status(raw: str | None, status_category: str | None = None) -> str:
        """Normalize status strings to canonical values."""
        if status_category:
            cat = status_category.lower().strip()
            category_map = {
                "new": "open",
                "to do": "open",
                "indeterminate": "in_progress",
                "in progress": "in_progress",
                "done": "done",
                "complete": "done",
            }
            if cat in category_map:
                return category_map[cat]

        if not raw:
            return "open"
        lower = raw.lower().strip()
        mapping = {
            # Common statuses
            "open": "open",
            "to do": "open",
            "todo": "open",
            "new": "open",
            "backlog": "open",
            "selected for development": "open",
            "in progress": "in_progress",
            "in development": "in_progress",
            "in review": "review",
            "review": "review",
            "code review": "review",
            "done": "done",
            "closed": "closed",
            "resolved": "done",
            "won't do": "closed",
            "wontfix": "closed",
            "duplicate": "closed",
            "cancelled": "closed",
            # GitLab
            "opened": "open",
            "merged": "done",
            "locked": "closed",
        }
        return mapping.get(lower, "open")

    @staticmethod
    def _normalize_item_type(raw: str | None) -> str:
        """Normalize work item type strings."""
        if not raw:
            return "task"
        lower = raw.lower().strip()
        mapping = {
            "epic": "epic",
            "story": "story",
            "user story": "story",
            "task": "task",
            "sub-task": "subtask",
            "subtask": "subtask",
            "sub_task": "subtask",
            "bug": "bug",
            "defect": "bug",
            "incident": "bug",
            "feature": "story",
            "improvement": "story",
            "enhancement": "story",
        }
        return mapping.get(lower, "task")
