"""Notion connector – database query with filter/sort & pagination.

Uses Notion API:
  POST /v1/databases/{database_id}/query
    Body: { filter, sorts, start_cursor, page_size }

Filters on last_edited_time >= since for incremental sync.

Auth: Bearer token (Internal Integration Token).
Rate limits: Notion returns 429 with Retry-After; 3 req/s average.
Pagination: response.has_more + response.next_cursor.
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

NOTION_API_BASE = "https://api.notion.com"
NOTION_API_VERSION = "2022-06-28"


class NotionConnector(BaseConnector):
    source = "notion"

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

        database_ids: list[str] = cfg.get("database_ids", [])
        if not database_ids:
            result.errors.append(
                "config.database_ids is required (list of Notion database IDs to query)"
            )
            return result

        # Resolve effective since from cursor
        state = await load_cursor(session, self.source, "page")
        effective_since = state.last_run if state and state.last_run > since else since

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

        async with self._make_client(token, base_url=NOTION_API_BASE, headers=headers) as client:
            for db_id in database_ids:
                await self._sync_database(client, session, db_id, effective_since, result)

        if result.ok and result.events_fetched > 0:
            now = datetime.now(timezone.utc)
            await save_cursor(session, self.source, "page", now)
            result.cursor_advanced = True

        await session.commit()
        return result

    async def _sync_database(
        self,
        client,
        session: AsyncSession,
        database_id: str,
        since: datetime,
        result: SyncResult,
    ) -> None:
        """POST /v1/databases/{id}/query with filter on last_edited_time."""
        start_cursor: str | None = None

        while True:
            body: dict = {
                "filter": {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {
                        "on_or_after": since.isoformat(),
                    },
                },
                "sorts": [
                    {
                        "timestamp": "last_edited_time",
                        "direction": "ascending",
                    }
                ],
                "page_size": 100,
            }
            if start_cursor:
                body["start_cursor"] = start_cursor

            resp = await request_with_retries(
                client,
                "POST",
                f"/v1/databases/{database_id}/query",
                json=body,
            )
            data = resp.json()

            pages = data.get("results", [])
            for page in pages:
                page_id = page.get("id", "")
                last_edited = page.get("last_edited_time", "")
                occurred_at = _parse_ts(last_edited) or datetime.now(timezone.utc)

                stored = await store_raw_event(
                    session, "notion", "page", page_id, occurred_at, page
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            if not data.get("has_more") or not pages:
                break
            start_cursor = data.get("next_cursor")
            if not start_cursor:
                break


# ── helpers ──────────────────────────────────────────────────────────


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
