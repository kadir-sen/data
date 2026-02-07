"""GitLab connector – issues, merge requests, and events.

Uses GitLab REST API v4:
  GET /api/v4/projects/:id/issues?updated_after=<ts>
  GET /api/v4/projects/:id/merge_requests?updated_after=<ts>
  GET /api/v4/projects/:id/events?after=<date>

Auth: Private-Token header or Bearer (OAuth).
Rate limits: GitLab returns 429 with Retry-After; we honour it.
Pagination: Link header with rel="next" or per_page/page params.
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


class GitLabConnector(BaseConnector):
    source = "gitlab"

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

        base_url = cfg.get("base_url", "https://gitlab.com").rstrip("/")
        project_id = cfg.get("project_id")
        if not project_id:
            result.errors.append("config.project_id is required (numeric ID or 'group/project')")
            return result

        # Resolve effective since from cursor
        state = await load_cursor(session, self.source, "issue")
        effective_since = state.last_run if state and state.last_run > since else since

        headers = {"PRIVATE-TOKEN": token}
        async with self._make_client(token, base_url=base_url, headers=headers) as client:
            project_path = _encode_project_id(project_id)

            await self._sync_issues(client, session, project_path, effective_since, result)
            await self._sync_merge_requests(client, session, project_path, effective_since, result)
            await self._sync_events(client, session, project_path, effective_since, result)

        if result.ok and result.events_fetched > 0:
            now = datetime.now(timezone.utc)
            await save_cursor(session, self.source, "issue", now)
            result.cursor_advanced = True

        await session.commit()
        return result

    # ── issues ───────────────────────────────────────────────────────

    async def _sync_issues(
        self, client, session: AsyncSession, project: str,
        since: datetime, result: SyncResult,
    ) -> None:
        page = 1
        per_page = 100

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                f"/api/v4/projects/{project}/issues",
                params={
                    "updated_after": since.isoformat(),
                    "per_page": per_page,
                    "page": page,
                    "scope": "all",
                },
            )
            issues = resp.json()
            if not isinstance(issues, list):
                break

            for issue in issues:
                iid = issue.get("iid", issue.get("id"))
                ns = issue.get("references", {}).get("full", f"{project}#{iid}")
                entity_id = ns if ns else f"{project}#{iid}"
                occurred_at = _parse_ts(issue.get("updated_at")) or datetime.now(timezone.utc)

                stored = await store_raw_event(
                    session, "gitlab", "issue", entity_id, occurred_at,
                    {"object_attributes": issue, "project": {"path_with_namespace": project}},
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            if len(issues) < per_page:
                break
            page += 1

    # ── merge requests ───────────────────────────────────────────────

    async def _sync_merge_requests(
        self, client, session: AsyncSession, project: str,
        since: datetime, result: SyncResult,
    ) -> None:
        page = 1
        per_page = 100

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                f"/api/v4/projects/{project}/merge_requests",
                params={
                    "updated_after": since.isoformat(),
                    "per_page": per_page,
                    "page": page,
                    "scope": "all",
                },
            )
            mrs = resp.json()
            if not isinstance(mrs, list):
                break

            for mr in mrs:
                iid = mr.get("iid", mr.get("id"))
                entity_id = f"{project}!{iid}"
                occurred_at = _parse_ts(mr.get("updated_at")) or datetime.now(timezone.utc)

                stored = await store_raw_event(
                    session, "gitlab", "merge_request", entity_id, occurred_at,
                    {"object_attributes": mr, "project": {"path_with_namespace": project}},
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            if len(mrs) < per_page:
                break
            page += 1

    # ── events (activity feed) ───────────────────────────────────────

    async def _sync_events(
        self, client, session: AsyncSession, project: str,
        since: datetime, result: SyncResult,
    ) -> None:
        page = 1
        per_page = 100

        while True:
            resp = await request_with_retries(
                client,
                "GET",
                f"/api/v4/projects/{project}/events",
                params={
                    "after": since.strftime("%Y-%m-%d"),
                    "per_page": per_page,
                    "page": page,
                },
            )
            events = resp.json()
            if not isinstance(events, list):
                break

            for ev in events:
                ev_id = str(ev.get("id", ""))
                action = ev.get("action_name", "unknown")
                occurred_at = _parse_ts(ev.get("created_at")) or datetime.now(timezone.utc)

                stored = await store_raw_event(
                    session, "gitlab", "event", ev_id, occurred_at,
                    {"event": ev, "action": action, "project": project},
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            if len(events) < per_page:
                break
            page += 1


# ── helpers ──────────────────────────────────────────────────────────


def _encode_project_id(project_id: str | int) -> str:
    """URL-encode project path (group/project → group%2Fproject) or return numeric id."""
    s = str(project_id)
    if "/" in s:
        import urllib.parse
        return urllib.parse.quote(s, safe="")
    return s


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
