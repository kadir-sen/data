"""Jira mapper: raw_event payload -> work_item, sprint, person, interaction_event."""

from __future__ import annotations

import logging
from typing import Any

from app.jobs.mappers.base import BaseMapper, MapperResult

logger = logging.getLogger(__name__)


class JiraMapper(BaseMapper):
    """Maps Jira webhook / API payloads to canonical entities.

    Handles entity_types: issue, sprint, comment, worklog.

    Configurable fields (via extra in raw_event or env):
        story_points_field: Custom field ID for story points (default: customfield_10016)
        sprint_field: Custom field ID for sprint (default: customfield_10020)
    """

    source = "jira"

    # Configurable Jira custom field IDs
    STORY_POINTS_FIELD = "customfield_10016"
    SPRINT_FIELD = "customfield_10020"
    EPIC_LINK_FIELD = "customfield_10014"

    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        dispatch = {
            "issue": self._map_issue,
            "sprint": self._map_sprint,
            "comment": self._map_comment,
            "worklog": self._map_worklog,
        }
        handler = dispatch.get(entity_type)
        if not handler:
            return MapperResult(errors=[f"Unsupported Jira entity_type: {entity_type}"])
        try:
            return handler(entity_id, payload)
        except Exception as exc:
            logger.exception("Jira mapper error for %s/%s", entity_type, entity_id)
            return MapperResult(errors=[f"Jira mapper error: {exc}"])

    # ── issue ─────────────────────────────────────────────────────────

    def _map_issue(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        # Support both webhook (issue inside payload) and direct API response
        issue = payload.get("issue", payload)
        fields = issue.get("fields", {})

        key = issue.get("key", entity_id)

        # Extract assignee as person
        assignee_raw = fields.get("assignee")
        if assignee_raw:
            result.persons.append({
                "source": "jira",
                "source_id": assignee_raw.get("accountId", assignee_raw.get("key", "")),
                "display_name": assignee_raw.get("displayName", "Unknown"),
                "email": assignee_raw.get("emailAddress"),
            })

        # Extract reporter as person
        reporter_raw = fields.get("reporter")
        if reporter_raw:
            result.persons.append({
                "source": "jira",
                "source_id": reporter_raw.get("accountId", reporter_raw.get("key", "")),
                "display_name": reporter_raw.get("displayName", "Unknown"),
                "email": reporter_raw.get("emailAddress"),
            })

        # Extract sprint(s) from custom field
        sprint_data = fields.get(self.SPRINT_FIELD)
        sprint_source_id = None
        if sprint_data:
            sprints = sprint_data if isinstance(sprint_data, list) else [sprint_data]
            for sp in sprints:
                if isinstance(sp, dict):
                    sp_id = str(sp.get("id", ""))
                    sprint_source_id = sprint_source_id or sp_id
                    result.sprints.append({
                        "source": "jira",
                        "source_id": sp_id,
                        "name": sp.get("name", ""),
                        "status": self._map_sprint_state(sp.get("state")),
                        "start_date": sp.get("startDate"),
                        "end_date": sp.get("endDate"),
                        "goal": sp.get("goal"),
                        "board_or_project": sp.get("originBoardId"),
                    })

        # Status + status category
        status_raw = self._safe_get(fields, "status", "name")
        status_category = self._safe_get(fields, "status", "statusCategory", "name")

        # Story points
        story_points = fields.get(self.STORY_POINTS_FIELD)
        if story_points is not None:
            try:
                story_points = float(story_points)
            except (TypeError, ValueError):
                story_points = None

        # Due date
        due_date = fields.get("duedate")

        # Labels
        labels = fields.get("labels", [])

        # Type
        issue_type = self._safe_get(fields, "issuetype", "name")

        # Priority
        priority_raw = self._safe_get(fields, "priority", "name")

        # Resolution date
        resolved_at = fields.get("resolutiondate")

        # Parent (epic link or parent field)
        parent_source_id = None
        parent_data = fields.get("parent")
        if parent_data:
            parent_source_id = parent_data.get("key")
        elif fields.get(self.EPIC_LINK_FIELD):
            parent_source_id = fields[self.EPIC_LINK_FIELD]

        # Build the work item
        result.work_items.append({
            "source": "jira",
            "source_id": key,
            "title": fields.get("summary", "Untitled"),
            "description": fields.get("description"),
            "item_type": self._normalize_item_type(issue_type),
            "status": self._normalize_status(status_raw, status_category),
            "priority": self._normalize_priority(priority_raw),
            "story_points": story_points,
            "due_date": due_date,
            "resolved_at": resolved_at,
            "labels": labels,
            "assignee_source": "jira",
            "assignee_source_id": (
                assignee_raw.get("accountId", assignee_raw.get("key"))
                if assignee_raw else None
            ),
            "sprint_source_id": sprint_source_id,
            "parent_source_id": parent_source_id,
            "extra": {
                "project_key": self._safe_get(fields, "project", "key"),
                "project_name": self._safe_get(fields, "project", "name"),
                "issue_id": issue.get("id"),
                "created": fields.get("created"),
                "updated": fields.get("updated"),
                "components": [c.get("name") for c in fields.get("components", [])],
                "fix_versions": [v.get("name") for v in fields.get("fixVersions", [])],
            },
            "_raw_changelog": fields.get("changelog"),
        })

        # Register external link
        self_url = self._safe_get(issue, "self")
        browse_url = None
        if self_url and key:
            base = self_url.split("/rest/")[0] if "/rest/" in self_url else ""
            browse_url = f"{base}/browse/{key}" if base else None
        result.external_links.append({
            "canonical_table": "work_item",
            "source": "jira",
            "external_id": key,
            "external_url": browse_url,
            "link_type": "auto",
            "confidence": 1.0,
        })

        return result

    # ── sprint ────────────────────────────────────────────────────────

    def _map_sprint(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        sp = payload.get("sprint", payload)
        result.sprints.append({
            "source": "jira",
            "source_id": str(sp.get("id", entity_id)),
            "name": sp.get("name", ""),
            "status": self._map_sprint_state(sp.get("state")),
            "start_date": sp.get("startDate"),
            "end_date": sp.get("endDate"),
            "goal": sp.get("goal"),
            "board_or_project": str(sp.get("originBoardId", "")),
            "extra": {k: v for k, v in sp.items() if k not in {
                "id", "name", "state", "startDate", "endDate", "goal", "originBoardId",
            }},
        })
        return result

    # ── comment ───────────────────────────────────────────────────────

    def _map_comment(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        comment = payload.get("comment", payload)
        author = comment.get("author", {})

        if author:
            result.persons.append({
                "source": "jira",
                "source_id": author.get("accountId", author.get("key", "")),
                "display_name": author.get("displayName", "Unknown"),
                "email": author.get("emailAddress"),
            })

        # The issue key this comment belongs to
        issue_key = self._safe_get(payload, "issue", "key")

        result.interaction_events.append({
            "source": "jira",
            "source_id": str(comment.get("id", entity_id)),
            "event_type": "comment",
            "channel_or_context": issue_key,
            "author_source": "jira",
            "author_source_id": author.get("accountId", author.get("key")) if author else None,
            "body": comment.get("body") if isinstance(comment.get("body"), str) else str(comment.get("body", "")),
            "work_item_source_id": issue_key,
            "occurred_at": comment.get("created"),
            "extra": {
                "updated": comment.get("updated"),
                "jsd_public": comment.get("jsdPublic"),
            },
        })
        return result

    # ── worklog ───────────────────────────────────────────────────────

    def _map_worklog(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        """Map Jira worklog entries to effort_log-compatible format.

        Stored in extra for the effort_log processor to handle.
        """
        result = MapperResult()
        worklog = payload.get("worklog", payload)
        author = worklog.get("author", {})

        if author:
            result.persons.append({
                "source": "jira",
                "source_id": author.get("accountId", author.get("key", "")),
                "display_name": author.get("displayName", "Unknown"),
                "email": author.get("emailAddress"),
            })
        return result

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _map_sprint_state(state: str | None) -> str:
        if not state:
            return "future"
        lower = state.lower()
        return {"active": "active", "closed": "closed", "future": "future"}.get(lower, "future")
