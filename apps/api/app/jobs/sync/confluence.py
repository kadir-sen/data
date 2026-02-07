"""Confluence Cloud connector – search by CQL for updated pages.

Uses Confluence REST API:
  GET /wiki/rest/api/content/search?cql=<CQL>&limit=<n>&start=<offset>

CQL filter: `lastModified >= "YYYY-MM-DD"` with expand=body.storage,history,metadata.labels

Auth: Basic (email:api-token) for Atlassian Cloud.
Rate limits: honours 429 + Retry-After.
Pagination: start/limit params; response includes `_links.next`.
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


class ConfluenceConnector(BaseConnector):
    source = "confluence"

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

        base_url = cfg.get("base_url", "").rstrip("/")
        if not base_url:
            result.errors.append("config.base_url is required (e.g. https://myco.atlassian.net)")
            return result

        space_key = cfg.get("space_key")  # optional filter
        email = cfg.get("email", "")

        # Resolve effective since from cursor
        state = await load_cursor(session, self.source, "page")
        effective_since = state.last_run if state and state.last_run > since else since

        # Auth
        if email:
            import base64

            b64 = base64.b64encode(f"{email}:{token}".encode()).decode()
            headers = {"Authorization": f"Basic {b64}"}
        else:
            headers = {"Authorization": f"Bearer {token}"}

        async with self._make_client(token, base_url=base_url, headers=headers) as client:
            await self._sync_pages(client, session, effective_since, result, space_key)

        if result.ok and result.events_fetched > 0:
            now = datetime.now(timezone.utc)
            await save_cursor(session, self.source, "page", now)
            result.cursor_advanced = True

        await session.commit()
        return result

    async def _sync_pages(
        self,
        client,
        session: AsyncSession,
        since: datetime,
        result: SyncResult,
        space_key: str | None = None,
    ) -> None:
        """Search Confluence via CQL for pages modified since `since`."""
        since_str = since.strftime("%Y-%m-%d")
        cql = f'lastModified >= "{since_str}" AND type = "page"'
        if space_key:
            cql += f' AND space = "{space_key}"'

        start = 0
        limit = 25  # Confluence default max

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                "/wiki/rest/api/content/search",
                params={
                    "cql": cql,
                    "start": start,
                    "limit": limit,
                    "expand": "body.storage,history,metadata.labels,space,version",
                },
            )
            data = resp.json()
            pages = data.get("results", [])

            for page in pages:
                page_id = str(page.get("id", ""))
                title = page.get("title", "")

                # Build occurred_at from history or version
                when = (
                    _safe_get(page, "version", "when")
                    or _safe_get(page, "history", "createdDate")
                )
                occurred_at = _parse_ts(when) or datetime.now(timezone.utc)

                stored = await store_raw_event(
                    session, "confluence", "page", page_id, occurred_at, page
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            # Pagination: check for _links.next
            next_link = _safe_get(data, "_links", "next")
            if not next_link or len(pages) < limit:
                break
            start += limit


# ── helpers ──────────────────────────────────────────────────────────


def _safe_get(d: dict, *keys: str) -> object:
    current: object = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _parse_ts(raw: object) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
