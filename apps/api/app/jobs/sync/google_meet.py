"""Google Meet connector – transcript entries.

Uses Google Meet REST API (conferenceRecords):
  GET /v2/conferenceRecords  (list meetings)
  GET /v2/conferenceRecords/{id}/transcripts
  GET /v2/conferenceRecords/{id}/transcripts/{tid}/entries

Note: Google Meet transcripts.entries.get returns individual transcript entries.
There may be a mismatch between Meet transcripts and Google Docs transcripts that
are auto-generated; this connector targets the Meet API directly.

Auth: Bearer token (OAuth 2.0 access token with meet.readonly scope).
Rate limits: standard Google API quotas; 429 with Retry-After.
Pagination: nextPageToken / pageToken pattern.
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

MEET_API_BASE = "https://meet.googleapis.com"


class GoogleMeetConnector(BaseConnector):
    source = "google_meet"

    async def sync(
        self,
        session: AsyncSession,
        token: str,
        since: datetime,
        *,
        config: dict | None = None,
    ) -> SyncResult:
        result = SyncResult(source=self.source)

        # Resolve effective since from cursor
        state = await load_cursor(session, self.source, "transcript")
        effective_since = state.last_run if state and state.last_run > since else since

        headers = {"Authorization": f"Bearer {token}"}

        async with self._make_client(token, base_url=MEET_API_BASE, headers=headers) as client:
            await self._sync_conference_records(client, session, effective_since, result)

        if result.ok and result.events_fetched > 0:
            now = datetime.now(timezone.utc)
            await save_cursor(session, self.source, "transcript", now)
            result.cursor_advanced = True

        await session.commit()
        return result

    async def _sync_conference_records(
        self,
        client,
        session: AsyncSession,
        since: datetime,
        result: SyncResult,
    ) -> None:
        """List conference records and fetch transcripts for each."""
        page_token: str | None = None

        while True:
            params: dict[str, object] = {
                "filter": f'end_time>"{since.isoformat()}"',
                "pageSize": 50,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await request_with_retries(
                client, "GET", "/v2/conferenceRecords", params=params,
            )
            data = resp.json()

            records = data.get("conferenceRecords", [])
            for record in records:
                record_name = record.get("name", "")  # e.g. "conferenceRecords/abc123"
                if not record_name:
                    continue

                await self._sync_transcripts(client, session, record_name, record, result)

            page_token = data.get("nextPageToken")
            if not page_token or not records:
                break

    async def _sync_transcripts(
        self,
        client,
        session: AsyncSession,
        record_name: str,
        record: dict,
        result: SyncResult,
    ) -> None:
        """List transcripts for a conference record, then fetch entries."""
        page_token: str | None = None

        while True:
            params: dict[str, object] = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token

            resp = await request_with_retries(
                client, "GET", f"/v2/{record_name}/transcripts", params=params,
            )
            data = resp.json()

            transcripts = data.get("transcripts", [])
            for transcript in transcripts:
                transcript_name = transcript.get("name", "")
                if not transcript_name:
                    continue

                await self._sync_transcript_entries(
                    client, session, transcript_name, record, result
                )

            page_token = data.get("nextPageToken")
            if not page_token or not transcripts:
                break

    async def _sync_transcript_entries(
        self,
        client,
        session: AsyncSession,
        transcript_name: str,
        record: dict,
        result: SyncResult,
    ) -> None:
        """GET transcript entries and store each as a raw_event."""
        page_token: str | None = None

        while True:
            params: dict[str, object] = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token

            resp = await request_with_retries(
                client, "GET", f"/v2/{transcript_name}/entries", params=params,
            )
            data = resp.json()

            entries = data.get("transcriptEntries", [])
            for entry in entries:
                entry_name = entry.get("name", "")
                # Build a composite entity_id from transcript + entry
                entity_id = entry_name or f"{transcript_name}/entry-{id(entry)}"

                start_time = entry.get("startOffset") or entry.get("startTime")
                occurred_at = _parse_ts(str(start_time)) if start_time else datetime.now(timezone.utc)

                # Combine entry with meeting metadata for the raw payload
                payload = {
                    "entry": entry,
                    "transcript_name": transcript_name,
                    "conference_record": record,
                }

                stored = await store_raw_event(
                    session, "google_meet", "transcript_entry", entity_id, occurred_at, payload
                )
                result.events_fetched += 1
                if stored:
                    result.events_stored += 1
                else:
                    result.events_skipped_duplicate += 1

            page_token = data.get("nextPageToken")
            if not page_token or not entries:
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
