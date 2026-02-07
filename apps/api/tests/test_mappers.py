"""Tests for source-specific mappers (pure unit tests, no DB required)."""

import pytest

from app.jobs.mappers.jira import JiraMapper
from app.jobs.mappers.gitlab import GitLabMapper
from app.jobs.mappers.notion import NotionMapper
from app.jobs.mappers.slack import SlackMapper
from app.jobs.mappers.confluence import ConfluenceMapper
from app.jobs.mappers.google_meet import GoogleMeetMapper
from app.jobs.mappers.base import BaseMapper


# ── BaseMapper helpers ────────────────────────────────────────────────


class TestBaseMapperHelpers:
    def test_normalize_priority(self):
        assert BaseMapper._normalize_priority("Highest") == "critical"
        assert BaseMapper._normalize_priority("blocker") == "critical"
        assert BaseMapper._normalize_priority("High") == "high"
        assert BaseMapper._normalize_priority("Medium") == "medium"
        assert BaseMapper._normalize_priority("Normal") == "medium"
        assert BaseMapper._normalize_priority("Low") == "low"
        assert BaseMapper._normalize_priority("Lowest") == "low"
        assert BaseMapper._normalize_priority("P0") == "critical"
        assert BaseMapper._normalize_priority("P1") == "high"
        assert BaseMapper._normalize_priority("P2") == "medium"
        assert BaseMapper._normalize_priority("P3") == "low"
        assert BaseMapper._normalize_priority(None) is None
        assert BaseMapper._normalize_priority("") is None

    def test_normalize_status(self):
        assert BaseMapper._normalize_status("To Do") == "open"
        assert BaseMapper._normalize_status("In Progress") == "in_progress"
        assert BaseMapper._normalize_status("Done") == "done"
        assert BaseMapper._normalize_status("Closed") == "closed"
        assert BaseMapper._normalize_status("Review") == "review"
        assert BaseMapper._normalize_status(None) == "open"

    def test_normalize_status_with_category(self):
        # Status category takes precedence
        assert BaseMapper._normalize_status("Whatever", "To Do") == "open"
        assert BaseMapper._normalize_status("Custom", "In Progress") == "in_progress"
        assert BaseMapper._normalize_status("Finished", "Done") == "done"

    def test_normalize_item_type(self):
        assert BaseMapper._normalize_item_type("Epic") == "epic"
        assert BaseMapper._normalize_item_type("Story") == "story"
        assert BaseMapper._normalize_item_type("Bug") == "bug"
        assert BaseMapper._normalize_item_type("Sub-Task") == "subtask"
        assert BaseMapper._normalize_item_type("Feature") == "story"
        assert BaseMapper._normalize_item_type("Unknown") == "task"
        assert BaseMapper._normalize_item_type(None) == "task"

    def test_safe_get(self):
        d = {"a": {"b": {"c": 42}}}
        assert BaseMapper._safe_get(d, "a", "b", "c") == 42
        assert BaseMapper._safe_get(d, "a", "b", "missing") is None
        assert BaseMapper._safe_get(d, "x") is None
        assert BaseMapper._safe_get(d, "x", default="fallback") == "fallback"


# ── Jira Mapper ───────────────────────────────────────────────────────


class TestJiraMapper:
    @pytest.fixture
    def mapper(self):
        return JiraMapper()

    def test_map_issue_basic(self, mapper: JiraMapper):
        payload = {
            "issue": {
                "key": "PROJ-123",
                "id": "10001",
                "self": "https://myco.atlassian.net/rest/api/2/issue/10001",
                "fields": {
                    "summary": "Fix login bug",
                    "description": "Users can't log in",
                    "issuetype": {"name": "Bug"},
                    "status": {
                        "name": "In Progress",
                        "statusCategory": {"name": "In Progress"},
                    },
                    "priority": {"name": "High"},
                    "assignee": {
                        "accountId": "abc123",
                        "displayName": "Jane Dev",
                        "emailAddress": "jane@example.com",
                    },
                    "reporter": {
                        "accountId": "def456",
                        "displayName": "Bob QA",
                    },
                    "labels": ["backend", "auth"],
                    "duedate": "2024-03-15",
                    "project": {"key": "PROJ", "name": "Project X"},
                    "customfield_10016": 5,  # story points
                },
            }
        }

        result = mapper.map("issue", "PROJ-123", payload)

        assert not result.has_errors
        assert len(result.work_items) == 1
        assert len(result.persons) == 2  # assignee + reporter

        wi = result.work_items[0]
        assert wi["source"] == "jira"
        assert wi["source_id"] == "PROJ-123"
        assert wi["title"] == "Fix login bug"
        assert wi["item_type"] == "bug"
        assert wi["status"] == "in_progress"
        assert wi["priority"] == "high"
        assert wi["story_points"] == 5.0
        assert wi["due_date"] == "2024-03-15"
        assert wi["labels"] == ["backend", "auth"]
        assert wi["assignee_source_id"] == "abc123"

    def test_map_issue_with_sprint(self, mapper: JiraMapper):
        payload = {
            "issue": {
                "key": "PROJ-456",
                "fields": {
                    "summary": "Add feature",
                    "issuetype": {"name": "Story"},
                    "status": {"name": "Open", "statusCategory": {"name": "To Do"}},
                    "customfield_10020": [
                        {
                            "id": 42,
                            "name": "Sprint 7",
                            "state": "active",
                            "startDate": "2024-03-01",
                            "endDate": "2024-03-15",
                            "goal": "Ship auth module",
                        }
                    ],
                    "project": {"key": "PROJ"},
                },
            }
        }

        result = mapper.map("issue", "PROJ-456", payload)

        assert not result.has_errors
        assert len(result.sprints) == 1
        sp = result.sprints[0]
        assert sp["name"] == "Sprint 7"
        assert sp["status"] == "active"
        assert sp["goal"] == "Ship auth module"

        wi = result.work_items[0]
        assert wi["sprint_source_id"] == "42"

    def test_map_sprint(self, mapper: JiraMapper):
        payload = {
            "sprint": {
                "id": 99,
                "name": "Sprint 10",
                "state": "closed",
                "startDate": "2024-01-01",
                "endDate": "2024-01-14",
                "goal": "MVP launch",
                "originBoardId": 5,
            }
        }

        result = mapper.map("sprint", "99", payload)

        assert not result.has_errors
        assert len(result.sprints) == 1
        sp = result.sprints[0]
        assert sp["source_id"] == "99"
        assert sp["status"] == "closed"

    def test_map_comment(self, mapper: JiraMapper):
        payload = {
            "issue": {"key": "PROJ-789"},
            "comment": {
                "id": "10500",
                "body": "This looks good to merge.",
                "author": {
                    "accountId": "user-1",
                    "displayName": "Alice",
                },
                "created": "2024-03-10T12:00:00Z",
            },
        }

        result = mapper.map("comment", "10500", payload)

        assert not result.has_errors
        assert len(result.interaction_events) == 1
        ie = result.interaction_events[0]
        assert ie["event_type"] == "comment"
        assert ie["channel_or_context"] == "PROJ-789"
        assert ie["body"] == "This looks good to merge."

    def test_map_unsupported_entity_type(self, mapper: JiraMapper):
        result = mapper.map("webhook_ping", "1", {})
        assert result.has_errors
        assert "Unsupported" in result.errors[0]

    def test_external_link_created(self, mapper: JiraMapper):
        payload = {
            "issue": {
                "key": "PROJ-1",
                "self": "https://myco.atlassian.net/rest/api/2/issue/1",
                "fields": {
                    "summary": "Test",
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Open"},
                    "project": {"key": "PROJ"},
                },
            }
        }
        result = mapper.map("issue", "PROJ-1", payload)
        assert len(result.external_links) == 1
        link = result.external_links[0]
        assert link["source"] == "jira"
        assert link["external_id"] == "PROJ-1"
        assert "browse/PROJ-1" in link["external_url"]


# ── GitLab Mapper ─────────────────────────────────────────────────────


class TestGitLabMapper:
    @pytest.fixture
    def mapper(self):
        return GitLabMapper()

    def test_map_issue(self, mapper: GitLabMapper):
        payload = {
            "object_attributes": {
                "iid": 42,
                "title": "Fix CI pipeline",
                "description": "Pipeline breaks on main",
                "state": "opened",
                "due_date": "2024-04-01",
                "weight": 3,
                "milestone": {
                    "id": 10,
                    "title": "v2.0",
                    "state": "active",
                    "start_date": "2024-03-01",
                    "due_date": "2024-03-31",
                },
                "web_url": "https://gitlab.com/team/proj/-/issues/42",
            },
            "project": {"path_with_namespace": "team/proj"},
            "labels": [{"title": "bug"}, {"title": "priority::high"}],
            "assignees": [
                {"id": 7, "name": "DevOps Dan", "username": "dand", "email": "dan@co.com"}
            ],
        }

        result = mapper.map("issue", "42", payload)

        assert not result.has_errors
        assert len(result.work_items) == 1
        wi = result.work_items[0]
        assert wi["source_id"] == "team/proj#42"
        assert wi["item_type"] == "bug"
        assert wi["priority"] == "high"
        assert wi["story_points"] == 3.0
        assert wi["status"] == "open"

        assert len(result.sprints) == 1
        assert result.sprints[0]["name"] == "v2.0"

    def test_map_milestone(self, mapper: GitLabMapper):
        payload = {
            "object_attributes": {
                "id": 55,
                "title": "Q1 Release",
                "state": "closed",
                "start_date": "2024-01-01",
                "due_date": "2024-03-31",
                "description": "All Q1 features",
            },
            "project": {"path_with_namespace": "org/repo"},
        }

        result = mapper.map("milestone", "55", payload)

        assert not result.has_errors
        assert len(result.sprints) == 1
        sp = result.sprints[0]
        assert sp["status"] == "closed"
        assert sp["source_id"] == "55"

    def test_map_note(self, mapper: GitLabMapper):
        payload = {
            "object_attributes": {
                "id": 100,
                "note": "LGTM!",
                "noteable_type": "Issue",
                "created_at": "2024-03-10T10:00:00Z",
            },
            "user": {"id": 3, "name": "Reviewer", "username": "rev"},
            "project": {"path_with_namespace": "org/repo"},
            "issue": {"iid": 42},
        }

        result = mapper.map("note", "100", payload)

        assert not result.has_errors
        assert len(result.interaction_events) == 1
        ie = result.interaction_events[0]
        assert ie["body"] == "LGTM!"
        assert ie["channel_or_context"] == "org/repo#42"

    def test_priority_extraction_from_labels(self):
        labels = ["backend", "priority::critical", "v2"]
        prio = GitLabMapper._extract_priority_from_labels(labels)
        assert prio == "critical"

    def test_points_extraction_from_labels(self):
        assert GitLabMapper._extract_points_from_labels(["SP: 5"]) == 5.0
        assert GitLabMapper._extract_points_from_labels(["points:3"]) == 3.0
        assert GitLabMapper._extract_points_from_labels(["no match"]) is None


# ── Notion Mapper ─────────────────────────────────────────────────────


class TestNotionMapper:
    @pytest.fixture
    def mapper(self):
        return NotionMapper()

    def test_map_task_page(self, mapper: NotionMapper):
        payload = {
            "id": "abc-def-123",
            "url": "https://www.notion.so/my-task-abcdef123",
            "created_time": "2024-03-01T10:00:00Z",
            "last_edited_time": "2024-03-05T14:00:00Z",
            "created_by": {"id": "user-1", "name": "Alice"},
            "parent": {"database_id": "db-001"},
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "Implement OAuth"}],
                },
                "Status": {
                    "type": "status",
                    "status": {"name": "In Progress"},
                },
                "Priority": {
                    "type": "select",
                    "select": {"name": "P1"},
                },
                "Story Points": {
                    "type": "number",
                    "number": 8,
                },
                "Assignee": {
                    "type": "people",
                    "people": [{"id": "user-2", "name": "Bob", "person": {"email": "bob@co.com"}}],
                },
                "Tags": {
                    "type": "multi_select",
                    "multi_select": [{"name": "task"}, {"name": "backend"}],
                },
                "Due Date": {
                    "type": "date",
                    "date": {"start": "2024-04-01"},
                },
            },
        }

        result = mapper.map("page", "abc-def-123", payload)

        assert not result.has_errors
        assert len(result.work_items) == 1
        assert len(result.doc_entries) == 0  # Tagged as task, not doc

        wi = result.work_items[0]
        assert wi["title"] == "Implement OAuth"
        assert wi["status"] == "in_progress"
        assert wi["priority"] == "high"  # P1 -> high
        assert wi["story_points"] == 8
        assert wi["due_date"] == "2024-04-01"

    def test_map_doc_page(self, mapper: NotionMapper):
        payload = {
            "id": "doc-page-1",
            "url": "https://www.notion.so/design-doc-123",
            "created_time": "2024-02-01T10:00:00Z",
            "created_by": {"id": "user-1", "name": "Carol"},
            "parent": {"database_id": "db-docs"},
            "properties": {
                "Title": {
                    "type": "title",
                    "title": [{"plain_text": "Architecture Design"}],
                },
                "Tags": {
                    "type": "multi_select",
                    "multi_select": [{"name": "design"}, {"name": "architecture"}],
                },
            },
        }

        result = mapper.map("page", "doc-page-1", payload)

        assert not result.has_errors
        assert len(result.work_items) == 0
        assert len(result.doc_entries) == 1

        doc = result.doc_entries[0]
        assert doc["title"] == "Architecture Design"
        assert doc["doc_type"] == "page"
        assert doc["source"] == "notion"


# ── Slack Mapper ──────────────────────────────────────────────────────


class TestSlackMapper:
    @pytest.fixture
    def mapper(self):
        return SlackMapper()

    def test_map_message(self, mapper: SlackMapper):
        payload = {
            "event": {
                "type": "message",
                "user": "U12345",
                "text": "Hey, can someone review PR #42?",
                "channel": "C0001",
                "ts": "1710000000.000001",
            }
        }

        result = mapper.map("message", "C0001:1710000000.000001", payload)

        assert not result.has_errors
        assert len(result.interaction_events) == 1
        ie = result.interaction_events[0]
        assert ie["event_type"] == "message"
        assert ie["channel_or_context"] == "C0001"
        assert "PR #42" in ie["body"]

    def test_map_thread_reply(self, mapper: SlackMapper):
        payload = {
            "event": {
                "type": "message",
                "user": "U99999",
                "text": "On it!",
                "channel": "C0001",
                "ts": "1710000001.000002",
                "thread_ts": "1710000000.000001",
            }
        }

        result = mapper.map("message", "thread-reply-1", payload)

        assert not result.has_errors
        ie = result.interaction_events[0]
        assert ie["event_type"] == "thread_reply"
        assert ie.get("parent_source_id") == "C0001:1710000000.000001"

    def test_map_reaction(self, mapper: SlackMapper):
        payload = {
            "event": {
                "type": "reaction_added",
                "user": "U12345",
                "reaction": "thumbsup",
                "item": {"type": "message", "channel": "C0001", "ts": "1710000000.000001"},
                "event_ts": "1710000005.000000",
            }
        }

        result = mapper.map("reaction", "reaction-1", payload)

        assert not result.has_errors
        ie = result.interaction_events[0]
        assert ie["event_type"] == "reaction"
        assert ie["body"] == ":thumbsup:"


# ── Confluence Mapper ─────────────────────────────────────────────────


class TestConfluenceMapper:
    @pytest.fixture
    def mapper(self):
        return ConfluenceMapper()

    def test_map_page(self, mapper: ConfluenceMapper):
        payload = {
            "id": "12345",
            "title": "Sprint Retrospective",
            "type": "page",
            "status": "current",
            "space": {"key": "ENG", "name": "Engineering"},
            "body": {
                "storage": {"value": "<p>Great sprint!</p>"},
            },
            "history": {
                "createdBy": {
                    "accountId": "author-1",
                    "displayName": "PM Pat",
                    "email": "pat@co.com",
                },
                "createdDate": "2024-03-10T10:00:00Z",
            },
            "metadata": {
                "labels": {
                    "results": [{"name": "retrospective"}, {"name": "sprint-7"}],
                },
            },
            "_links": {
                "base": "https://myco.atlassian.net/wiki",
                "webui": "/spaces/ENG/pages/12345/Sprint+Retrospective",
            },
        }

        result = mapper.map("page", "12345", payload)

        assert not result.has_errors
        assert len(result.doc_entries) == 1
        doc = result.doc_entries[0]
        assert doc["title"] == "Sprint Retrospective"
        assert doc["space_or_parent"] == "ENG"
        assert doc["labels"] == ["retrospective", "sprint-7"]
        assert "wiki" in doc["url"]

    def test_map_comment(self, mapper: ConfluenceMapper):
        payload = {
            "id": "comment-1",
            "body": {"storage": {"value": "Great doc!"}},
            "container": {"id": "12345"},
            "version": {
                "by": {"accountId": "user-x", "displayName": "Commenter"},
                "when": "2024-03-11T09:00:00Z",
                "number": 1,
            },
        }

        result = mapper.map("comment", "comment-1", payload)

        assert not result.has_errors
        assert len(result.interaction_events) == 1
        ie = result.interaction_events[0]
        assert ie["event_type"] == "comment"
        assert ie["body"] == "Great doc!"


# ── Google Meet Mapper ────────────────────────────────────────────────


class TestGoogleMeetMapper:
    @pytest.fixture
    def mapper(self):
        return GoogleMeetMapper()

    def test_map_transcript(self, mapper: GoogleMeetMapper):
        payload = {
            "title": "Weekly Standup",
            "meetingId": "meet-abc-123",
            "hangoutLink": "https://meet.google.com/abc-123",
            "startTime": "2024-03-10T09:00:00Z",
            "endTime": "2024-03-10T09:30:00Z",
            "durationMinutes": 30,
            "organizer": {
                "id": "org-1",
                "displayName": "Tech Lead",
                "email": "lead@co.com",
            },
            "participants": [
                {"id": "p1", "displayName": "Dev A", "email": "a@co.com"},
                {"id": "p2", "displayName": "Dev B", "email": "b@co.com"},
            ],
            "transcript": [
                {"speaker": "Tech Lead", "text": "Let's start with updates."},
                {"speaker": "Dev A", "text": "I finished the auth module."},
            ],
        }

        result = mapper.map("transcript", "meet-abc-123", payload)

        assert not result.has_errors
        assert len(result.doc_entries) == 1
        doc = result.doc_entries[0]
        assert doc["title"] == "Transcript: Weekly Standup"
        assert doc["doc_type"] == "transcript"
        assert "[Tech Lead]" in doc["body_text"]
        assert "[Dev A]" in doc["body_text"]

        # 2 participants + 1 organizer
        assert len(result.persons) == 3

    def test_map_recording(self, mapper: GoogleMeetMapper):
        payload = {
            "title": "Design Review",
            "meetingId": "meet-xyz",
            "recordingUrl": "https://drive.google.com/file/d/abc",
            "startTime": "2024-03-10T14:00:00Z",
        }

        result = mapper.map("recording", "rec-1", payload)

        assert not result.has_errors
        assert len(result.doc_entries) == 1
        doc = result.doc_entries[0]
        assert doc["title"] == "Recording: Design Review"
        assert doc["doc_type"] == "meeting_notes"


# ── Cross-system linker (unit) ────────────────────────────────────────


class TestLinker:
    def test_extract_links_from_text(self):
        from app.jobs.linker import extract_links_from_text

        text = """
        See the Jira ticket: https://myco.atlassian.net/browse/PROJ-123
        And the GitLab issue: https://gitlab.com/org/repo/-/issues/42
        Also check Confluence: https://myco.atlassian.net/wiki/spaces/ENG/pages/99999/Some+Page
        """

        links = extract_links_from_text(text)

        assert len(links) == 3

        sources = {l["source"] for l in links}
        assert "jira" in sources
        assert "gitlab" in sources
        assert "confluence" in sources

        jira_link = next(l for l in links if l["source"] == "jira")
        assert jira_link["external_id"] == "PROJ-123"
        assert jira_link["canonical_table"] == "work_item"

        gitlab_link = next(l for l in links if l["source"] == "gitlab")
        assert gitlab_link["external_id"] == "org/repo#42"

        confluence_link = next(l for l in links if l["source"] == "confluence")
        assert confluence_link["external_id"] == "99999"

    def test_extract_links_empty_text(self):
        from app.jobs.linker import extract_links_from_text
        assert extract_links_from_text("") == []
        assert extract_links_from_text("no urls here") == []


# ── Mapper registry ──────────────────────────────────────────────────


class TestMapperRegistry:
    def test_all_sources_registered(self):
        from app.jobs.mappers import MAPPER_REGISTRY
        assert "jira" in MAPPER_REGISTRY
        assert "gitlab" in MAPPER_REGISTRY
        assert "notion" in MAPPER_REGISTRY
        assert "slack" in MAPPER_REGISTRY
        assert "confluence" in MAPPER_REGISTRY
        assert "google_meet" in MAPPER_REGISTRY

    def test_all_mappers_are_base_mapper_subclasses(self):
        from app.jobs.mappers import MAPPER_REGISTRY
        for name, cls in MAPPER_REGISTRY.items():
            assert issubclass(cls, BaseMapper), f"{name} is not a BaseMapper subclass"
