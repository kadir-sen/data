"""Jira Software Cloud (Agile) connector.

Pulls board → sprint → issues-for-sprint using the Agile REST API:
  GET /rest/agile/1.0/board/{boardId}/sprint
  GET /rest/agile/1.0/board/{boardId}/sprint/{sprintId}/issue

Also pulls standalone sprints and issues updated since the cursor.

Auth: Basic auth (email:api-token) or Bearer (OAuth/PAT).
Rate limits: Jira Cloud enforces per-tenant limits; we honour 429 + Retry-After.
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


class JiraConnector(BaseConnector):
    source = "jira"

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

        board_id = cfg.get("board_id")
        email = cfg.get("email", "")

        # Resolve effective since from cursor
        state = await load_cursor(session, self.source, "issue")
        effective_since = state.last_run if state and state.last_run > since else since

        # Auth: Basic (email:token) if email provided, else Bearer
        if email:
            import base64

            b64 = base64.b64encode(f"{email}:{token}".encode()).decode()
            headers = {"Authorization": f"Basic {b64}"}
        else:
            headers = {"Authorization": f"Bearer {token}"}

        async with self._make_client(token, base_url=base_url, headers=headers) as client:
            if board_id:
                await self._sync_board_sprints(
                    client, session, board_id, effective_since, result
                )
            else:
                # Fallback: search issues updated since timestamp
                await self._sync_search(client, session, effective_since, result)

        # Advance cursor on success
        if result.ok and result.events_fetched > 0:
            now = datetime.now(timezone.utc)
            await save_cursor(session, self.source, "issue", now)
            result.cursor_advanced = True

        await session.commit()
        return result

    # ── board / sprint / issues ──────────────────────────────────────

    async def _sync_board_sprints(
        self,
        client,
        session: AsyncSession,
        board_id: str | int,
        since: datetime,
        result: SyncResult,
    ) -> None:
        """Fetch sprints for a board, then issues for each sprint."""
        start_at = 0
        page_size = 50

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                f"/rest/agile/1.0/board/{board_id}/sprint",
                params={"startAt": start_at, "maxResults": page_size},
            )
            data = resp.json()
            sprints = data.get("values", [])

            for sp in sprints:
                sprint_id = sp.get("id")
                if not sprint_id:
                    continue

                # Store sprint as raw_event
                occurred_at = _parse_ts(sp.get("startDate")) or datetime.now(timezone.utc)
                stored = await store_raw_event(
                    session, "jira", "sprint", str(sprint_id), occurred_at, sp
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

                # Fetch issues for this sprint
                await self._sync_sprint_issues(
                    client, session, board_id, sprint_id, since, result
                )

            if data.get("isLast", True) or len(sprints) < page_size:
                break
            start_at += page_size

    async def _sync_sprint_issues(
        self,
        client,
        session: AsyncSession,
        board_id: str | int,
        sprint_id: int,
        since: datetime,
        result: SyncResult,
    ) -> None:
        """GET /rest/agile/1.0/board/{boardId}/sprint/{sprintId}/issue with pagination."""
        start_at = 0
        page_size = 50

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                f"/rest/agile/1.0/board/{board_id}/sprint/{sprint_id}/issue",
                params={
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": "*all",
                },
            )
            data = resp.json()
            issues = data.get("issues", [])

            for issue in issues:
                fields = issue.get("fields", {})
                updated_str = fields.get("updated") or fields.get("created")
                updated_at = _parse_ts(updated_str)
                if updated_at and updated_at < since:
                    continue

                key = issue.get("key", str(issue.get("id", "")))
                occurred_at = updated_at or datetime.now(timezone.utc)
                stored = await store_raw_event(
                    session, "jira", "issue", key, occurred_at, {"issue": issue}
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            total = data.get("total", 0)
            if start_at + page_size >= total or not issues:
                break
            start_at += page_size

    # ── JQL search fallback ──────────────────────────────────────────

    async def _sync_search(
        self,
        client,
        session: AsyncSession,
        since: datetime,
        result: SyncResult,
    ) -> None:
        """Fallback: search all issues updated since timestamp via JQL."""
        since_str = since.strftime("%Y-%m-%d %H:%M")
        jql = f'updated >= "{since_str}"'
        start_at = 0
        page_size = 50

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                "/rest/api/3/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": "*all",
                },
            )
            data = resp.json()
            issues = data.get("issues", [])

            for issue in issues:
                fields = issue.get("fields", {})
                updated_str = fields.get("updated") or fields.get("created")
                key = issue.get("key", str(issue.get("id", "")))
                occurred_at = _parse_ts(updated_str) or datetime.now(timezone.utc)

                stored = await store_raw_event(
                    session, "jira", "issue", key, occurred_at, {"issue": issue}
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            total = data.get("total", 0)
            if start_at + page_size >= total or not issues:
                break
            start_at += page_size


# ── helpers ──────────────────────────────────────────────────────────


def _parse_ts(raw: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string, returning None on failure."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
