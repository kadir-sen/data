"""Slack mapper: raw_event payload -> interaction_event, person."""

from __future__ import annotations

import logging
from typing import Any

from app.jobs.mappers.base import BaseMapper, MapperResult

logger = logging.getLogger(__name__)


class SlackMapper(BaseMapper):
    """Maps Slack Events API / webhook payloads to canonical entities.

    Handles entity_types: message, reaction.
    """

    source = "slack"

    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        dispatch = {
            "message": self._map_message,
            "reaction": self._map_reaction,
        }
        handler = dispatch.get(entity_type)
        if not handler:
            return MapperResult(errors=[f"Unsupported Slack entity_type: {entity_type}"])
        try:
            return handler(entity_id, payload)
        except Exception as exc:
            logger.exception("Slack mapper error for %s/%s", entity_type, entity_id)
            return MapperResult(errors=[f"Slack mapper error: {exc}"])

    def _map_message(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        # Slack Events API wraps the event
        event = payload.get("event", payload)

        user_id = event.get("user", "")
        if user_id:
            result.persons.append({
                "source": "slack",
                "source_id": user_id,
                "display_name": user_id,  # Resolved later via Slack users.info
                "email": None,
            })

        channel = event.get("channel", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts")

        # Determine event type
        is_thread_reply = thread_ts is not None and thread_ts != ts
        event_type = "thread_reply" if is_thread_reply else "message"

        source_id = f"{channel}:{ts}" if channel and ts else entity_id

        result.interaction_events.append({
            "source": "slack",
            "source_id": source_id,
            "event_type": event_type,
            "channel_or_context": channel,
            "author_source": "slack",
            "author_source_id": user_id or None,
            "body": event.get("text", ""),
            "work_item_source_id": None,
            "occurred_at": self._ts_to_iso(ts),
            "extra": {
                "thread_ts": thread_ts,
                "subtype": event.get("subtype"),
                "team": event.get("team", payload.get("team_id")),
                "blocks": event.get("blocks"),
                "files": [f.get("name") for f in event.get("files", [])],
                "reactions": event.get("reactions"),
            },
        })

        # If this is a thread reply, register the parent thread
        if is_thread_reply:
            result.interaction_events[-1]["parent_source_id"] = f"{channel}:{thread_ts}"

        return result

    def _map_reaction(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        event = payload.get("event", payload)

        user_id = event.get("user", "")
        if user_id:
            result.persons.append({
                "source": "slack",
                "source_id": user_id,
                "display_name": user_id,
                "email": None,
            })

        item = event.get("item", {})
        channel = item.get("channel", "")
        ts = item.get("ts", "")
        reaction = event.get("reaction", "")

        source_id = f"{channel}:{ts}:reaction:{user_id}:{reaction}"

        result.interaction_events.append({
            "source": "slack",
            "source_id": source_id,
            "event_type": "reaction",
            "channel_or_context": channel,
            "author_source": "slack",
            "author_source_id": user_id or None,
            "body": f":{reaction}:",
            "work_item_source_id": None,
            "occurred_at": self._ts_to_iso(event.get("event_ts", ts)),
            "extra": {
                "reaction": reaction,
                "item_type": item.get("type"),
                "item_ts": ts,
            },
        })
        return result

    @staticmethod
    def _ts_to_iso(ts: str) -> str | None:
        """Convert Slack timestamp (epoch.micro) to ISO format."""
        if not ts:
            return None
        try:
            from datetime import datetime, timezone
            epoch = float(ts)
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            return ts
