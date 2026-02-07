"""Slack connector – conversations.history for channels.

Uses Slack Web API:
  GET conversations.history?channel=<id>&oldest=<ts>&latest=<ts>&limit=200

Supports oldest/latest parameters for incremental windowing.
Optionally, the Slack Events API can be used for push-based collection;
this connector focuses on the pull-based conversations.history approach.

Auth: Bearer token (Bot User OAuth Token).
Rate limits: Slack returns 429 with Retry-After header; tier 3 for conversations.history.
Pagination: response_metadata.next_cursor for cursor-based pagination.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.sync.base import (
    BaseConnector,
    SyncResult,
    load_cursor,
    request_with_retries,
    save_cursor,
    store_raw_event,
)

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackConnector(BaseConnector):
    source = "slack"

    async def sync(
        self,
        session: AsyncSession,
        token: str,
        since: datetime,
        *,
        config: dict | None = None,
    ) -> SyncResult:
        result = SyncResult(source=self.source)
        cfg = config or {}

        channels: list[str] = cfg.get("channels", [])
        if not channels:
            result.errors.append(
                "config.channels is required (list of channel IDs to sync, e.g. ['C0001', 'C0002'])"
            )
            return result

        # Resolve effective since from cursor
        state = await load_cursor(session, self.source, "message")
        effective_since = state.last_run if state and state.last_run > since else since
        oldest_ts = str(effective_since.timestamp())

        headers = {"Authorization": f"Bearer {token}"}

        async with self._make_client(token, base_url=SLACK_API_BASE, headers=headers) as client:
            for channel_id in channels:
                await self._sync_channel(
                    client, session, channel_id, oldest_ts, result
                )

        if result.ok and result.events_fetched > 0:
            now = datetime.now(timezone.utc)
            await save_cursor(session, self.source, "message", now)
            result.cursor_advanced = True

        await session.commit()
        return result

    async def _sync_channel(
        self,
        client,
        session: AsyncSession,
        channel_id: str,
        oldest_ts: str,
        result: SyncResult,
    ) -> None:
        """Pull message history for a single channel using cursor pagination."""
        cursor: str | None = None

        while True:
            params: dict[str, object] = {
                "channel": channel_id,
                "oldest": oldest_ts,
                "limit": 200,
                "inclusive": "true",
            }
            if cursor:
                params["cursor"] = cursor

            resp = await request_with_retries(client, "GET", "/conversations.history", params=params)
            data = resp.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                logger.warning("Slack API error for channel %s: %s", channel_id, error)
                result.errors.append(f"Slack conversations.history error: {error}")
                return

            messages = data.get("messages", [])

            for msg in messages:
                ts = msg.get("ts", "")
                user = msg.get("user", msg.get("bot_id", "unknown"))
                entity_id = f"{channel_id}:{ts}"

                # Convert Slack ts to datetime
                occurred_at = _slack_ts_to_datetime(ts)

                stored = await store_raw_event(
                    session, "slack", "message", entity_id, occurred_at,
                    {
                        "event": {
                            "type": msg.get("type", "message"),
                            "subtype": msg.get("subtype"),
                            "user": user,
                            "text": msg.get("text", ""),
                            "channel": channel_id,
                            "ts": ts,
                            "thread_ts": msg.get("thread_ts"),
                            "reactions": msg.get("reactions"),
                            "files": msg.get("files"),
                        }
                    },
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            # Cursor-based pagination
            next_cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not next_cursor or not messages:
                break
            cursor = next_cursor


# ── helpers ──────────────────────────────────────────────────────────


def _slack_ts_to_datetime(ts: str) -> datetime:
    """Convert Slack timestamp '1234567890.123456' to UTC datetime."""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return datetime.now(timezone.utc)
