"""Confluence mapper: raw_event payload -> doc_entry, person, interaction_event."""

from __future__ import annotations

import logging
from typing import Any

from app.jobs.mappers.base import BaseMapper, MapperResult

logger = logging.getLogger(__name__)


class ConfluenceMapper(BaseMapper):
    """Maps Confluence webhook / REST API payloads to canonical entities.

    Handles entity_types: page, blogpost, comment.
    """

    source = "confluence"

    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        dispatch = {
            "page": self._map_page,
            "blogpost": self._map_page,
            "comment": self._map_comment,
        }
        handler = dispatch.get(entity_type)
        if not handler:
            return MapperResult(errors=[f"Unsupported Confluence entity_type: {entity_type}"])
        try:
            return handler(entity_id, payload, entity_type)
        except Exception as exc:
            logger.exception("Confluence mapper error for %s/%s", entity_type, entity_id)
            return MapperResult(errors=[f"Confluence mapper error: {exc}"])

    def _map_page(
        self, entity_id: str, payload: dict[str, Any], entity_type: str = "page"
    ) -> MapperResult:
        result = MapperResult()
        page = payload.get("page", payload)

        # Author
        creator = page.get("history", {}).get("createdBy", page.get("version", {}).get("by", {}))
        if not creator:
            creator = page.get("_expandable", {})
        if creator.get("accountId") or creator.get("username"):
            result.persons.append({
                "source": "confluence",
                "source_id": creator.get("accountId", creator.get("username", "")),
                "display_name": creator.get("displayName", creator.get("publicName", "Unknown")),
                "email": creator.get("email"),
            })

        # Labels
        labels_raw = page.get("metadata", {}).get("labels", {}).get("results", [])
        labels = [lb.get("name", "") for lb in labels_raw if isinstance(lb, dict)]

        # Space
        space = page.get("space", {})
        space_key = space.get("key", "")

        # Body text (storage format or plain)
        body = page.get("body", {})
        body_text = (
            body.get("view", {}).get("value")
            or body.get("storage", {}).get("value")
            or body.get("plain", {}).get("value")
        )

        # Links
        base_url = page.get("_links", {}).get("base", "")
        web_ui = page.get("_links", {}).get("webui", "")
        url = f"{base_url}{web_ui}" if base_url and web_ui else None

        doc_type = "page" if entity_type == "page" else "page"

        result.doc_entries.append({
            "source": "confluence",
            "source_id": str(page.get("id", entity_id)),
            "title": page.get("title", "Untitled"),
            "doc_type": doc_type,
            "url": url,
            "body_text": body_text,
            "author_source": "confluence",
            "author_source_id": creator.get("accountId", creator.get("username")) if creator else None,
            "space_or_parent": space_key,
            "labels": labels,
            "occurred_at": page.get("history", {}).get("createdDate"),
            "extra": {
                "version": page.get("version", {}).get("number"),
                "space_name": space.get("name"),
                "status": page.get("status"),
                "type": page.get("type"),
                "ancestors": [a.get("id") for a in page.get("ancestors", [])],
            },
        })

        result.external_links.append({
            "canonical_table": "doc_entry",
            "source": "confluence",
            "external_id": str(page.get("id", entity_id)),
            "external_url": url,
            "link_type": "auto",
            "confidence": 1.0,
        })

        return result

    def _map_comment(
        self, entity_id: str, payload: dict[str, Any], entity_type: str = "comment"
    ) -> MapperResult:
        result = MapperResult()
        comment = payload.get("comment", payload)

        author = comment.get("version", {}).get("by", {})
        if author.get("accountId") or author.get("username"):
            result.persons.append({
                "source": "confluence",
                "source_id": author.get("accountId", author.get("username", "")),
                "display_name": author.get("displayName", "Unknown"),
                "email": author.get("email"),
            })

        # The page this comment is on
        container = comment.get("container", comment.get("_expandable", {}))
        page_id = container.get("id") if isinstance(container, dict) else None

        body = comment.get("body", {})
        body_text = (
            body.get("view", {}).get("value")
            or body.get("storage", {}).get("value")
            or ""
        )

        result.interaction_events.append({
            "source": "confluence",
            "source_id": str(comment.get("id", entity_id)),
            "event_type": "comment",
            "channel_or_context": f"confluence:page:{page_id}" if page_id else None,
            "author_source": "confluence",
            "author_source_id": author.get("accountId", author.get("username")) if author else None,
            "body": body_text,
            "work_item_source_id": None,
            "doc_entry_source_id": str(page_id) if page_id else None,
            "occurred_at": comment.get("version", {}).get("when"),
            "extra": {
                "page_id": page_id,
                "version": comment.get("version", {}).get("number"),
            },
        })
        return result
