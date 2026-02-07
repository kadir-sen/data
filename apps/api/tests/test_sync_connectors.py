"""Unit tests for incremental sync connectors with mocked HTTP.

Tests verify:
- Each connector fetches data, stores raw_events, and advances cursor
- Idempotency: running sync twice does not duplicate raw_events
- Rate-limit retries with exponential backoff
- Pagination handling
- Error handling for missing config
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.sync.base import (
    SyncResult,
    compute_content_hash,
    request_with_retries,
    store_raw_event,
)
from app.jobs.sync.jira import JiraConnector
from app.jobs.sync.gitlab import GitLabConnector
from app.jobs.sync.confluence import ConfluenceConnector
from app.jobs.sync.slack import SlackConnector
from app.jobs.sync.notion import NotionConnector
from app.jobs.sync.google_meet import GoogleMeetConnector
from app.models.raw_event import RawEvent
from app.models.source_state import SourceState


SINCE = datetime(2024, 1, 1, tzinfo=timezone.utc)
FAKE_TOKEN = "test-token-12345"


# ── helpers ──────────────────────────────────────────────────────────


def _mock_response(data: dict, status_code: int = 200, headers: dict | None = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=data,
        headers=headers or {},
        request=httpx.Request("GET", "https://test.example.com"),
    )


# ── Base: compute_content_hash ───────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("jira", "issue", "PROJ-1", {"key": "value"})
        h2 = compute_content_hash("jira", "issue", "PROJ-1", {"key": "value"})
        assert h1 == h2

    def test_different_payload_different_hash(self):
        h1 = compute_content_hash("jira", "issue", "PROJ-1", {"key": "a"})
        h2 = compute_content_hash("jira", "issue", "PROJ-1", {"key": "b"})
        assert h1 != h2

    def test_different_entity_different_hash(self):
        h1 = compute_content_hash("jira", "issue", "PROJ-1", {"key": "v"})
        h2 = compute_content_hash("jira", "issue", "PROJ-2", {"key": "v"})
        assert h1 != h2


# ── Base: request_with_retries ───────────────────────────────────────


class TestRequestWithRetries:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=_mock_response({"ok": True}))

        resp = await request_with_retries(mock_client, "GET", "/test")
        assert resp.json() == {"ok": True}
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        resp_429 = _mock_response({}, status_code=429, headers={"Retry-After": "0.01"})
        resp_ok = _mock_response({"ok": True})

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=[resp_429, resp_ok])

        resp = await request_with_retries(
            mock_client, "GET", "/test", initial_backoff=0.01
        )
        assert resp.json() == {"ok": True}
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        resp_500 = _mock_response({}, status_code=500)
        resp_ok = _mock_response({"ok": True})

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=[resp_500, resp_ok])

        resp = await request_with_retries(
            mock_client, "GET", "/test", initial_backoff=0.01
        )
        assert resp.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_raises_on_4xx(self):
        resp_400 = httpx.Response(
            status_code=400,
            json={"error": "bad request"},
            request=httpx.Request("GET", "https://test.example.com/test"),
        )
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=resp_400)

        with pytest.raises(httpx.HTTPStatusError):
            await request_with_retries(mock_client, "GET", "/test")

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        resp_429 = _mock_response({}, status_code=429, headers={"Retry-After": "0.01"})

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=resp_429)

        with pytest.raises(httpx.HTTPError, match="Max retries"):
            await request_with_retries(
                mock_client, "GET", "/test", max_retries=2, initial_backoff=0.01
            )


# ── Jira Connector ───────────────────────────────────────────────────


class TestJiraConnector:
    @pytest.fixture
    def connector(self):
        return JiraConnector()

    def _make_sprint_response(self, sprints: list[dict], is_last: bool = True) -> dict:
        return {"values": sprints, "isLast": is_last}

    def _make_issue_response(self, issues: list[dict], total: int | None = None) -> dict:
        return {"issues": issues, "total": total or len(issues)}

    @pytest.mark.asyncio
    async def test_missing_base_url(self, connector: JiraConnector):
        session = AsyncMock(spec=AsyncSession)
        result = await connector.sync(session, FAKE_TOKEN, SINCE, config={})
        assert not result.ok
        assert "base_url" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_board_sprints_and_issues(self, connector: JiraConnector):
        sprint_data = {
            "id": 42,
            "name": "Sprint 7",
            "state": "active",
            "startDate": "2024-03-01T00:00:00Z",
        }
        issue_data = {
            "key": "PROJ-1",
            "id": "10001",
            "fields": {
                "summary": "Test issue",
                "updated": "2024-06-01T10:00:00Z",
                "created": "2024-01-15T10:00:00Z",
                "issuetype": {"name": "Story"},
                "status": {"name": "Open"},
            },
        }

        sprint_resp = _mock_response(self._make_sprint_response([sprint_data]))
        issues_resp = _mock_response(self._make_issue_response([issue_data]))

        call_count = 0
        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "/sprint" in url and "/issue" not in url:
                return sprint_resp
            return issues_resp

        with patch("app.jobs.sync.jira.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.jira.load_cursor", return_value=None):
                with patch("app.jobs.sync.jira.save_cursor", return_value=None):
                    with patch("app.jobs.sync.jira.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"base_url": "https://myco.atlassian.net", "board_id": "5"},
                        )

        assert result.ok
        assert result.events_fetched == 2  # 1 sprint + 1 issue
        assert result.events_stored == 2

    @pytest.mark.asyncio
    async def test_sync_search_fallback(self, connector: JiraConnector):
        """When no board_id, falls back to JQL search."""
        issue_data = {
            "key": "PROJ-2",
            "fields": {
                "summary": "Search result",
                "updated": "2024-06-01T10:00:00Z",
                "issuetype": {"name": "Task"},
                "status": {"name": "Done"},
            },
        }

        search_resp = _mock_response({"issues": [issue_data], "total": 1})

        async def mock_request(method, url, **kwargs):
            return search_resp

        with patch("app.jobs.sync.jira.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.jira.load_cursor", return_value=None):
                with patch("app.jobs.sync.jira.save_cursor", return_value=None):
                    with patch("app.jobs.sync.jira.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"base_url": "https://myco.atlassian.net"},
                        )

        assert result.ok
        assert result.events_fetched == 1

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_skipped(self, connector: JiraConnector):
        """Second sync skips already-stored events."""
        issue_data = {
            "key": "PROJ-1",
            "fields": {"summary": "Dup", "updated": "2024-06-01T10:00:00Z"},
        }
        search_resp = _mock_response({"issues": [issue_data], "total": 1})

        async def mock_request(method, url, **kwargs):
            return search_resp

        with patch("app.jobs.sync.jira.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.jira.load_cursor", return_value=None):
                with patch("app.jobs.sync.jira.save_cursor", return_value=None):
                    # First run: stored
                    with patch("app.jobs.sync.jira.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        r1 = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"base_url": "https://myco.atlassian.net"},
                        )

                    # Second run: duplicate (store returns False)
                    with patch("app.jobs.sync.jira.store_raw_event", return_value=False):
                        session = AsyncMock(spec=AsyncSession)
                        r2 = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"base_url": "https://myco.atlassian.net"},
                        )

        assert r1.events_stored == 1
        assert r2.events_stored == 0
        assert r2.events_skipped_duplicate == 1


# ── GitLab Connector ─────────────────────────────────────────────────


class TestGitLabConnector:
    @pytest.fixture
    def connector(self):
        return GitLabConnector()

    @pytest.mark.asyncio
    async def test_missing_project_id(self, connector: GitLabConnector):
        session = AsyncMock(spec=AsyncSession)
        result = await connector.sync(session, FAKE_TOKEN, SINCE, config={})
        assert not result.ok
        assert "project_id" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_issues_and_mrs(self, connector: GitLabConnector):
        issue = {
            "iid": 42,
            "title": "Fix CI",
            "state": "opened",
            "updated_at": "2024-06-01T10:00:00Z",
            "references": {"full": "group/repo#42"},
        }
        mr = {
            "iid": 10,
            "title": "Add feature",
            "state": "merged",
            "updated_at": "2024-06-01T11:00:00Z",
        }
        event = {
            "id": 999,
            "action_name": "pushed to",
            "created_at": "2024-06-01T12:00:00Z",
        }

        call_count = {"issues": 0, "mrs": 0, "events": 0}

        async def mock_request(method, url, **kwargs):
            if "/issues" in url:
                call_count["issues"] += 1
                return _mock_response([issue] if call_count["issues"] == 1 else [])
            elif "/merge_requests" in url:
                call_count["mrs"] += 1
                return _mock_response([mr] if call_count["mrs"] == 1 else [])
            elif "/events" in url:
                call_count["events"] += 1
                return _mock_response([event] if call_count["events"] == 1 else [])
            return _mock_response([])

        with patch("app.jobs.sync.gitlab.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.gitlab.load_cursor", return_value=None):
                with patch("app.jobs.sync.gitlab.save_cursor", return_value=None):
                    with patch("app.jobs.sync.gitlab.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"project_id": "group/repo"},
                        )

        assert result.ok
        assert result.events_fetched == 3  # 1 issue + 1 MR + 1 event
        assert result.events_stored == 3

    @pytest.mark.asyncio
    async def test_pagination(self, connector: GitLabConnector):
        """Test that multiple pages of issues are fetched."""
        page1 = [{"iid": i, "updated_at": "2024-06-01T10:00:00Z"} for i in range(100)]
        page2 = [{"iid": 100, "updated_at": "2024-06-01T10:00:00Z"}]

        issue_call = {"count": 0}

        async def mock_request(method, url, **kwargs):
            if "/issues" in url:
                issue_call["count"] += 1
                if issue_call["count"] == 1:
                    return _mock_response(page1)
                elif issue_call["count"] == 2:
                    return _mock_response(page2)
                return _mock_response([])
            return _mock_response([])

        with patch("app.jobs.sync.gitlab.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.gitlab.load_cursor", return_value=None):
                with patch("app.jobs.sync.gitlab.save_cursor", return_value=None):
                    with patch("app.jobs.sync.gitlab.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"project_id": "123"},
                        )

        assert result.events_fetched >= 101


# ── Confluence Connector ─────────────────────────────────────────────


class TestConfluenceConnector:
    @pytest.fixture
    def connector(self):
        return ConfluenceConnector()

    @pytest.mark.asyncio
    async def test_missing_base_url(self, connector: ConfluenceConnector):
        session = AsyncMock(spec=AsyncSession)
        result = await connector.sync(session, FAKE_TOKEN, SINCE, config={})
        assert not result.ok
        assert "base_url" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_pages(self, connector: ConfluenceConnector):
        page = {
            "id": "12345",
            "title": "Sprint Retro",
            "type": "page",
            "version": {"when": "2024-06-01T10:00:00Z"},
            "space": {"key": "ENG"},
        }
        search_resp = _mock_response({"results": [page], "_links": {}})

        async def mock_request(method, url, **kwargs):
            return search_resp

        with patch("app.jobs.sync.confluence.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.confluence.load_cursor", return_value=None):
                with patch("app.jobs.sync.confluence.save_cursor", return_value=None):
                    with patch("app.jobs.sync.confluence.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"base_url": "https://myco.atlassian.net"},
                        )

        assert result.ok
        assert result.events_fetched == 1
        assert result.events_stored == 1

    @pytest.mark.asyncio
    async def test_space_filter_in_cql(self, connector: ConfluenceConnector):
        """Verify space_key is included in CQL when provided."""
        captured_params: list[dict] = []

        async def mock_request(method, url, **kwargs):
            if kwargs.get("params"):
                captured_params.append(dict(kwargs["params"]))
            return _mock_response({"results": [], "_links": {}})

        with patch("app.jobs.sync.confluence.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.confluence.load_cursor", return_value=None):
                with patch("app.jobs.sync.confluence.save_cursor", return_value=None):
                    session = AsyncMock(spec=AsyncSession)
                    await connector.sync(
                        session, FAKE_TOKEN, SINCE,
                        config={"base_url": "https://test.atlassian.net", "space_key": "DEV"},
                    )

        assert len(captured_params) == 1
        assert 'space = "DEV"' in captured_params[0]["cql"]


# ── Slack Connector ──────────────────────────────────────────────────


class TestSlackConnector:
    @pytest.fixture
    def connector(self):
        return SlackConnector()

    @pytest.mark.asyncio
    async def test_missing_channels(self, connector: SlackConnector):
        session = AsyncMock(spec=AsyncSession)
        result = await connector.sync(session, FAKE_TOKEN, SINCE, config={})
        assert not result.ok
        assert "channels" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_messages(self, connector: SlackConnector):
        msg1 = {
            "type": "message",
            "user": "U12345",
            "text": "Hello world",
            "ts": "1710000000.000001",
        }
        msg2 = {
            "type": "message",
            "user": "U67890",
            "text": "Reply here",
            "ts": "1710000001.000002",
            "thread_ts": "1710000000.000001",
        }
        history_resp = _mock_response({
            "ok": True,
            "messages": [msg1, msg2],
            "response_metadata": {"next_cursor": ""},
        })

        async def mock_request(method, url, **kwargs):
            return history_resp

        with patch("app.jobs.sync.slack.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.slack.load_cursor", return_value=None):
                with patch("app.jobs.sync.slack.save_cursor", return_value=None):
                    with patch("app.jobs.sync.slack.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"channels": ["C0001"]},
                        )

        assert result.ok
        assert result.events_fetched == 2
        assert result.events_stored == 2

    @pytest.mark.asyncio
    async def test_slack_api_error(self, connector: SlackConnector):
        """Slack returns ok=false."""
        error_resp = _mock_response({"ok": False, "error": "channel_not_found"})

        async def mock_request(method, url, **kwargs):
            return error_resp

        with patch("app.jobs.sync.slack.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.slack.load_cursor", return_value=None):
                with patch("app.jobs.sync.slack.save_cursor", return_value=None):
                    session = AsyncMock(spec=AsyncSession)
                    result = await connector.sync(
                        session, FAKE_TOKEN, SINCE,
                        config={"channels": ["C_INVALID"]},
                    )

        assert not result.ok
        assert "channel_not_found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_cursor_pagination(self, connector: SlackConnector):
        """Test Slack cursor-based pagination."""
        page1 = _mock_response({
            "ok": True,
            "messages": [{"type": "message", "user": "U1", "text": "p1", "ts": "1710000000.000001"}],
            "response_metadata": {"next_cursor": "cursor_abc"},
        })
        page2 = _mock_response({
            "ok": True,
            "messages": [{"type": "message", "user": "U2", "text": "p2", "ts": "1710000001.000002"}],
            "response_metadata": {"next_cursor": ""},
        })

        call_count = {"n": 0}

        async def mock_request(method, url, **kwargs):
            call_count["n"] += 1
            return page1 if call_count["n"] == 1 else page2

        with patch("app.jobs.sync.slack.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.slack.load_cursor", return_value=None):
                with patch("app.jobs.sync.slack.save_cursor", return_value=None):
                    with patch("app.jobs.sync.slack.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"channels": ["C0001"]},
                        )

        assert result.events_fetched == 2


# ── Notion Connector ─────────────────────────────────────────────────


class TestNotionConnector:
    @pytest.fixture
    def connector(self):
        return NotionConnector()

    @pytest.mark.asyncio
    async def test_missing_database_ids(self, connector: NotionConnector):
        session = AsyncMock(spec=AsyncSession)
        result = await connector.sync(session, FAKE_TOKEN, SINCE, config={})
        assert not result.ok
        assert "database_ids" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_database_pages(self, connector: NotionConnector):
        page = {
            "id": "page-abc",
            "last_edited_time": "2024-06-01T10:00:00Z",
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": "My Task"}]},
            },
        }
        query_resp = _mock_response({
            "results": [page],
            "has_more": False,
            "next_cursor": None,
        })

        async def mock_request(method, url, **kwargs):
            return query_resp

        with patch("app.jobs.sync.notion.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.notion.load_cursor", return_value=None):
                with patch("app.jobs.sync.notion.save_cursor", return_value=None):
                    with patch("app.jobs.sync.notion.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"database_ids": ["db-001"]},
                        )

        assert result.ok
        assert result.events_fetched == 1
        assert result.events_stored == 1

    @pytest.mark.asyncio
    async def test_notion_pagination(self, connector: NotionConnector):
        """Test Notion has_more + next_cursor pagination."""
        page1 = {"id": "p1", "last_edited_time": "2024-06-01T10:00:00Z", "properties": {}}
        page2 = {"id": "p2", "last_edited_time": "2024-06-01T11:00:00Z", "properties": {}}

        call_count = {"n": 0}

        async def mock_request(method, url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _mock_response({
                    "results": [page1],
                    "has_more": True,
                    "next_cursor": "cursor_xyz",
                })
            return _mock_response({
                "results": [page2],
                "has_more": False,
                "next_cursor": None,
            })

        with patch("app.jobs.sync.notion.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.notion.load_cursor", return_value=None):
                with patch("app.jobs.sync.notion.save_cursor", return_value=None):
                    with patch("app.jobs.sync.notion.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"database_ids": ["db-001"]},
                        )

        assert result.events_fetched == 2

    @pytest.mark.asyncio
    async def test_filter_includes_since(self, connector: NotionConnector):
        """Verify the POST body contains last_edited_time filter."""
        captured_bodies: list[dict] = []

        async def mock_request(method, url, **kwargs):
            if kwargs.get("json"):
                captured_bodies.append(kwargs["json"])
            return _mock_response({"results": [], "has_more": False})

        with patch("app.jobs.sync.notion.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.notion.load_cursor", return_value=None):
                with patch("app.jobs.sync.notion.save_cursor", return_value=None):
                    session = AsyncMock(spec=AsyncSession)
                    await connector.sync(
                        session, FAKE_TOKEN, SINCE,
                        config={"database_ids": ["db-001"]},
                    )

        assert len(captured_bodies) == 1
        body = captured_bodies[0]
        assert body["filter"]["timestamp"] == "last_edited_time"
        assert "on_or_after" in body["filter"]["last_edited_time"]


# ── Google Meet Connector ────────────────────────────────────────────


class TestGoogleMeetConnector:
    @pytest.fixture
    def connector(self):
        return GoogleMeetConnector()

    @pytest.mark.asyncio
    async def test_sync_transcript_entries(self, connector: GoogleMeetConnector):
        record = {
            "name": "conferenceRecords/abc123",
            "space": {"meetingUri": "https://meet.google.com/abc-123"},
        }
        transcript = {"name": "conferenceRecords/abc123/transcripts/t1"}
        entry = {
            "name": "conferenceRecords/abc123/transcripts/t1/entries/e1",
            "participant": {"displayName": "Alice"},
            "text": "Hello everyone",
            "startOffset": "2024-06-01T09:00:00Z",
        }

        call_urls: list[str] = []

        async def mock_request(method, url, **kwargs):
            call_urls.append(url)
            if "conferenceRecords" == url.split("/v2/")[-1].split("/")[0] and "/transcripts" not in url:
                return _mock_response({"conferenceRecords": [record]})
            elif "/entries" in url:
                return _mock_response({"transcriptEntries": [entry]})
            elif "/transcripts" in url:
                return _mock_response({"transcripts": [transcript]})
            return _mock_response({})

        with patch("app.jobs.sync.google_meet.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.google_meet.load_cursor", return_value=None):
                with patch("app.jobs.sync.google_meet.save_cursor", return_value=None):
                    with patch("app.jobs.sync.google_meet.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(session, FAKE_TOKEN, SINCE)

        assert result.ok
        assert result.events_fetched >= 1
        assert result.events_stored >= 1

    @pytest.mark.asyncio
    async def test_no_records_no_error(self, connector: GoogleMeetConnector):
        """No conference records means zero events, no errors."""
        async def mock_request(method, url, **kwargs):
            return _mock_response({"conferenceRecords": []})

        with patch("app.jobs.sync.google_meet.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.google_meet.load_cursor", return_value=None):
                with patch("app.jobs.sync.google_meet.save_cursor", return_value=None):
                    session = AsyncMock(spec=AsyncSession)
                    result = await connector.sync(session, FAKE_TOKEN, SINCE)

        assert result.ok
        assert result.events_fetched == 0


# ── Connector Registry ───────────────────────────────────────────────


class TestConnectorRegistry:
    def test_all_sources_registered(self):
        from app.jobs.sync import CONNECTOR_REGISTRY

        expected = {"jira", "gitlab", "confluence", "slack", "notion", "google_meet"}
        assert set(CONNECTOR_REGISTRY.keys()) == expected

    def test_all_are_base_connector_subclasses(self):
        from app.jobs.sync import CONNECTOR_REGISTRY, BaseConnector

        for name, cls in CONNECTOR_REGISTRY.items():
            assert issubclass(cls, BaseConnector), f"{name} is not a BaseConnector subclass"


# ── SyncResult ───────────────────────────────────────────────────────


class TestSyncResult:
    def test_ok_when_no_errors(self):
        r = SyncResult(source="test")
        assert r.ok

    def test_not_ok_when_errors(self):
        r = SyncResult(source="test", errors=["something went wrong"])
        assert not r.ok

    def test_summary_keys(self):
        r = SyncResult(source="test", events_fetched=5, events_stored=3, events_skipped_duplicate=2)
        s = r.summary()
        assert s["source"] == "test"
        assert s["events_fetched"] == 5
        assert s["events_stored"] == 3
        assert s["events_skipped_duplicate"] == 2


# ── Cursor state idempotency (integration-style with mock DB) ────────


class TestCursorIdempotency:
    @pytest.mark.asyncio
    async def test_cursor_advances_on_success(self):
        """Verify cursor is saved after a successful sync."""
        connector = JiraConnector()
        issue_data = {
            "key": "PROJ-1",
            "fields": {"summary": "Test", "updated": "2024-06-01T10:00:00Z"},
        }

        async def mock_request(method, url, **kwargs):
            return _mock_response({"issues": [issue_data], "total": 1})

        save_calls: list[tuple] = []

        async def mock_save_cursor(session, source, entity_type, last_run, **kw):
            save_calls.append((source, entity_type, last_run))

        with patch("app.jobs.sync.jira.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.jira.load_cursor", return_value=None):
                with patch("app.jobs.sync.jira.save_cursor", side_effect=mock_save_cursor):
                    with patch("app.jobs.sync.jira.store_raw_event", return_value=True):
                        session = AsyncMock(spec=AsyncSession)
                        result = await connector.sync(
                            session, FAKE_TOKEN, SINCE,
                            config={"base_url": "https://test.atlassian.net"},
                        )

        assert result.cursor_advanced
        assert len(save_calls) == 1
        assert save_calls[0][0] == "jira"
        assert save_calls[0][1] == "issue"

    @pytest.mark.asyncio
    async def test_cursor_not_advanced_on_zero_events(self):
        """Cursor should not advance if no events were fetched."""
        connector = JiraConnector()

        async def mock_request(method, url, **kwargs):
            return _mock_response({"issues": [], "total": 0})

        save_calls: list = []

        async def mock_save_cursor(session, source, entity_type, last_run, **kw):
            save_calls.append(True)

        with patch("app.jobs.sync.jira.request_with_retries", side_effect=mock_request):
            with patch("app.jobs.sync.jira.load_cursor", return_value=None):
                with patch("app.jobs.sync.jira.save_cursor", side_effect=mock_save_cursor):
                    session = AsyncMock(spec=AsyncSession)
                    result = await connector.sync(
                        session, FAKE_TOKEN, SINCE,
                        config={"base_url": "https://test.atlassian.net"},
                    )

        assert not result.cursor_advanced
        assert len(save_calls) == 0
