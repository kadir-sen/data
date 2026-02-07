"""Notion mapper: raw_event payload -> work_item, doc_entry, person."""

from __future__ import annotations

import logging
from typing import Any

from app.jobs.mappers.base import BaseMapper, MapperResult

logger = logging.getLogger(__name__)


class NotionMapper(BaseMapper):
    """Maps Notion API payloads to canonical entities.

    Handles entity_types: page, database_item.

    Mapping rules:
        - Pages tagged "task" (via property or tag) -> work_item
        - Other pages -> doc_entry
        - Database items with Status/Priority/Points properties -> work_item
    """

    source = "notion"

    # Property names to look for (configurable)
    STATUS_PROP = "Status"
    PRIORITY_PROP = "Priority"
    POINTS_PROP = "Story Points"
    ASSIGNEE_PROP = "Assignee"
    DUE_DATE_PROP = "Due Date"
    TYPE_PROP = "Type"
    SPRINT_PROP = "Sprint"
    TAGS_PROP = "Tags"

    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        if entity_type in ("page", "database_item"):
            return self._map_page(entity_id, payload)
        return MapperResult(errors=[f"Unsupported Notion entity_type: {entity_type}"])

    def _map_page(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        properties = payload.get("properties", {})

        title = self._extract_title(properties, payload)
        tags = self._extract_multi_select(properties, self.TAGS_PROP)

        is_task = self._is_task_page(properties, tags)

        # Extract person from assignee
        assignee_info = self._extract_person_property(properties, self.ASSIGNEE_PROP)
        if assignee_info:
            result.persons.append({
                "source": "notion",
                "source_id": assignee_info["id"],
                "display_name": assignee_info["name"],
                "email": assignee_info.get("email"),
            })

        # Created by
        created_by = payload.get("created_by", {})
        if created_by.get("id"):
            result.persons.append({
                "source": "notion",
                "source_id": created_by["id"],
                "display_name": created_by.get("name", "Unknown"),
                "email": created_by.get("person", {}).get("email"),
            })

        if is_task:
            self._build_work_item(result, entity_id, payload, properties, title, tags, assignee_info)
        else:
            self._build_doc_entry(result, entity_id, payload, properties, title, tags, created_by)

        return result

    def _build_work_item(
        self,
        result: MapperResult,
        entity_id: str,
        payload: dict[str, Any],
        properties: dict[str, Any],
        title: str,
        tags: list[str],
        assignee_info: dict[str, Any] | None,
    ) -> None:
        status_raw = self._extract_status(properties, self.STATUS_PROP)
        priority_raw = self._extract_select(properties, self.PRIORITY_PROP)
        item_type_raw = self._extract_select(properties, self.TYPE_PROP)
        story_points = self._extract_number(properties, self.POINTS_PROP)
        due_date = self._extract_date(properties, self.DUE_DATE_PROP)
        sprint_name = self._extract_select(properties, self.SPRINT_PROP)

        result.work_items.append({
            "source": "notion",
            "source_id": entity_id,
            "title": title,
            "description": None,  # Notion page body requires separate API call
            "item_type": self._normalize_item_type(item_type_raw),
            "status": self._normalize_status(status_raw),
            "priority": self._normalize_priority(priority_raw),
            "story_points": story_points,
            "due_date": due_date,
            "resolved_at": None,
            "labels": tags,
            "assignee_source": "notion" if assignee_info else None,
            "assignee_source_id": assignee_info["id"] if assignee_info else None,
            "sprint_source_id": None,  # Notion doesn't have native sprints
            "parent_source_id": self._safe_get(payload, "parent", "page_id"),
            "extra": {
                "notion_url": payload.get("url"),
                "database_id": self._safe_get(payload, "parent", "database_id"),
                "created_time": payload.get("created_time"),
                "last_edited_time": payload.get("last_edited_time"),
                "sprint_name": sprint_name,
                "archived": payload.get("archived", False),
            },
        })

        result.external_links.append({
            "canonical_table": "work_item",
            "source": "notion",
            "external_id": entity_id,
            "external_url": payload.get("url"),
            "link_type": "auto",
            "confidence": 1.0,
        })

    def _build_doc_entry(
        self,
        result: MapperResult,
        entity_id: str,
        payload: dict[str, Any],
        properties: dict[str, Any],
        title: str,
        tags: list[str],
        created_by: dict[str, Any],
    ) -> None:
        result.doc_entries.append({
            "source": "notion",
            "source_id": entity_id,
            "title": title,
            "doc_type": "page",
            "url": payload.get("url"),
            "body_text": None,
            "author_source": "notion",
            "author_source_id": created_by.get("id"),
            "space_or_parent": self._safe_get(payload, "parent", "database_id")
                or self._safe_get(payload, "parent", "workspace"),
            "labels": tags,
            "occurred_at": payload.get("created_time"),
            "extra": {
                "last_edited_time": payload.get("last_edited_time"),
                "archived": payload.get("archived", False),
                "cover": payload.get("cover"),
                "icon": payload.get("icon"),
            },
        })

        result.external_links.append({
            "canonical_table": "doc_entry",
            "source": "notion",
            "external_id": entity_id,
            "external_url": payload.get("url"),
            "link_type": "auto",
            "confidence": 1.0,
        })

    # ── property extraction helpers ───────────────────────────────────

    @staticmethod
    def _is_task_page(properties: dict[str, Any], tags: list[str]) -> bool:
        """Determine if a Notion page is a task (vs a plain document)."""
        if "task" in [t.lower() for t in tags]:
            return True
        # Has Status property -> likely a task DB
        if "Status" in properties:
            prop = properties["Status"]
            if prop.get("type") in ("status", "select"):
                return True
        return False

    @staticmethod
    def _extract_title(properties: dict[str, Any], payload: dict[str, Any]) -> str:
        """Extract page title from Notion properties."""
        for prop in properties.values():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts) or "Untitled"
        return "Untitled"

    @staticmethod
    def _extract_status(properties: dict[str, Any], prop_name: str) -> str | None:
        prop = properties.get(prop_name, {})
        ptype = prop.get("type")
        if ptype == "status":
            status = prop.get("status")
            return status.get("name") if status else None
        if ptype == "select":
            select = prop.get("select")
            return select.get("name") if select else None
        return None

    @staticmethod
    def _extract_select(properties: dict[str, Any], prop_name: str) -> str | None:
        prop = properties.get(prop_name, {})
        if prop.get("type") == "select":
            select = prop.get("select")
            return select.get("name") if select else None
        return None

    @staticmethod
    def _extract_multi_select(properties: dict[str, Any], prop_name: str) -> list[str]:
        prop = properties.get(prop_name, {})
        if prop.get("type") == "multi_select":
            return [item.get("name", "") for item in prop.get("multi_select", [])]
        return []

    @staticmethod
    def _extract_number(properties: dict[str, Any], prop_name: str) -> float | None:
        prop = properties.get(prop_name, {})
        if prop.get("type") == "number":
            return prop.get("number")
        return None

    @staticmethod
    def _extract_date(properties: dict[str, Any], prop_name: str) -> str | None:
        prop = properties.get(prop_name, {})
        if prop.get("type") == "date":
            date_obj = prop.get("date")
            return date_obj.get("start") if date_obj else None
        return None

    @staticmethod
    def _extract_person_property(properties: dict[str, Any], prop_name: str) -> dict[str, Any] | None:
        prop = properties.get(prop_name, {})
        if prop.get("type") == "people":
            people = prop.get("people", [])
            if people:
                p = people[0]
                return {
                    "id": p.get("id", ""),
                    "name": p.get("name", "Unknown"),
                    "email": p.get("person", {}).get("email"),
                }
        return None
