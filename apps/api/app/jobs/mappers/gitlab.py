"""GitLab mapper: raw_event payload -> work_item, sprint, person, interaction_event."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.jobs.mappers.base import BaseMapper, MapperResult

logger = logging.getLogger(__name__)


class GitLabMapper(BaseMapper):
    """Maps GitLab webhook / API payloads to canonical entities.

    Handles entity_types: issue, merge_request, milestone, note.

    Sprint mapping:
        GitLab milestones -> sprint table.
        Labels matching "priority::*" -> priority.
    """

    source = "gitlab"

    def map(self, entity_type: str, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        dispatch = {
            "issue": self._map_issue,
            "merge_request": self._map_merge_request,
            "milestone": self._map_milestone,
            "note": self._map_note,
        }
        handler = dispatch.get(entity_type)
        if not handler:
            return MapperResult(errors=[f"Unsupported GitLab entity_type: {entity_type}"])
        try:
            return handler(entity_id, payload)
        except Exception as exc:
            logger.exception("GitLab mapper error for %s/%s", entity_type, entity_id)
            return MapperResult(errors=[f"GitLab mapper error: {exc}"])

    # ── issue ─────────────────────────────────────────────────────────

    def _map_issue(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        # GitLab webhook wraps in object_attributes; API response is flat
        issue = payload.get("object_attributes", payload)
        project = payload.get("project", {})

        labels = payload.get("labels", issue.get("labels", []))
        label_names = [
            lb.get("title", lb) if isinstance(lb, dict) else str(lb) for lb in labels
        ]

        # Assignees
        assignees = payload.get("assignees", [])
        if not assignees:
            assignee_data = issue.get("assignee")
            if assignee_data:
                assignees = [assignee_data] if isinstance(assignee_data, dict) else []

        for a in assignees:
            result.persons.append({
                "source": "gitlab",
                "source_id": str(a.get("id", "")),
                "display_name": a.get("name", a.get("username", "Unknown")),
                "email": a.get("email"),
            })

        # Milestone -> sprint
        milestone = issue.get("milestone")
        milestone_source_id = None
        if milestone:
            milestone_source_id = str(milestone.get("id", ""))
            result.sprints.append({
                "source": "gitlab",
                "source_id": milestone_source_id,
                "name": milestone.get("title", ""),
                "status": self._map_milestone_state(milestone.get("state")),
                "start_date": milestone.get("start_date"),
                "end_date": milestone.get("due_date"),
                "board_or_project": project.get("path_with_namespace"),
            })

        # Extract priority from labels
        priority = self._extract_priority_from_labels(label_names)

        # Extract story points from labels or weight field
        story_points = issue.get("weight")
        if story_points is None:
            story_points = self._extract_points_from_labels(label_names)

        # Item type heuristic from labels
        item_type = self._extract_type_from_labels(label_names)

        source_id = f"{project.get('path_with_namespace', '')}#{issue.get('iid', entity_id)}"

        result.work_items.append({
            "source": "gitlab",
            "source_id": source_id,
            "title": issue.get("title", "Untitled"),
            "description": issue.get("description"),
            "item_type": item_type,
            "status": self._normalize_status(issue.get("state")),
            "priority": priority,
            "story_points": float(story_points) if story_points is not None else None,
            "due_date": issue.get("due_date"),
            "resolved_at": issue.get("closed_at"),
            "labels": label_names,
            "assignee_source": "gitlab",
            "assignee_source_id": str(assignees[0].get("id", "")) if assignees else None,
            "sprint_source_id": milestone_source_id,
            "parent_source_id": None,
            "extra": {
                "project": project.get("path_with_namespace"),
                "iid": issue.get("iid"),
                "global_id": issue.get("id"),
                "web_url": issue.get("url", issue.get("web_url")),
                "confidential": issue.get("confidential"),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
            },
        })

        web_url = issue.get("url", issue.get("web_url"))
        result.external_links.append({
            "canonical_table": "work_item",
            "source": "gitlab",
            "external_id": source_id,
            "external_url": web_url,
            "link_type": "auto",
            "confidence": 1.0,
        })

        return result

    # ── merge_request ─────────────────────────────────────────────────

    def _map_merge_request(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        mr = payload.get("object_attributes", payload)
        project = payload.get("project", {})

        author = mr.get("author", payload.get("user", {}))
        if author:
            result.persons.append({
                "source": "gitlab",
                "source_id": str(author.get("id", "")),
                "display_name": author.get("name", author.get("username", "Unknown")),
                "email": author.get("email"),
            })

        source_id = f"{project.get('path_with_namespace', '')}!{mr.get('iid', entity_id)}"
        status = mr.get("state", "opened")
        if mr.get("merged_at") or status == "merged":
            canonical_status = "done"
        elif status == "closed":
            canonical_status = "closed"
        else:
            canonical_status = "in_progress" if mr.get("work_in_progress") else "review"

        result.work_items.append({
            "source": "gitlab",
            "source_id": source_id,
            "title": mr.get("title", "Untitled MR"),
            "description": mr.get("description"),
            "item_type": "task",
            "status": canonical_status,
            "priority": None,
            "story_points": None,
            "due_date": None,
            "resolved_at": mr.get("merged_at") or mr.get("closed_at"),
            "labels": [lb.get("title", lb) if isinstance(lb, dict) else str(lb) for lb in payload.get("labels", [])],
            "assignee_source": "gitlab",
            "assignee_source_id": str(author.get("id", "")) if author else None,
            "sprint_source_id": None,
            "parent_source_id": None,
            "extra": {
                "project": project.get("path_with_namespace"),
                "iid": mr.get("iid"),
                "source_branch": mr.get("source_branch"),
                "target_branch": mr.get("target_branch"),
                "web_url": mr.get("url", mr.get("web_url")),
                "merge_request": True,
            },
        })
        return result

    # ── milestone ─────────────────────────────────────────────────────

    def _map_milestone(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        ms = payload.get("object_attributes", payload)
        project = payload.get("project", {})

        result.sprints.append({
            "source": "gitlab",
            "source_id": str(ms.get("id", entity_id)),
            "name": ms.get("title", ""),
            "status": self._map_milestone_state(ms.get("state")),
            "start_date": ms.get("start_date"),
            "end_date": ms.get("due_date"),
            "board_or_project": project.get("path_with_namespace"),
            "extra": {
                "description": ms.get("description"),
                "web_url": ms.get("web_url"),
            },
        })
        return result

    # ── note (comment) ────────────────────────────────────────────────

    def _map_note(self, entity_id: str, payload: dict[str, Any]) -> MapperResult:
        result = MapperResult()
        note = payload.get("object_attributes", payload)
        user = note.get("author", payload.get("user", {}))
        project = payload.get("project", {})

        if user:
            result.persons.append({
                "source": "gitlab",
                "source_id": str(user.get("id", "")),
                "display_name": user.get("name", user.get("username", "Unknown")),
                "email": user.get("email"),
            })

        # Determine context (what the note is on)
        noteable_type = note.get("noteable_type", "")
        context = None
        work_item_source_id = None
        if noteable_type == "Issue" and payload.get("issue"):
            iid = payload["issue"].get("iid")
            proj = project.get("path_with_namespace", "")
            context = f"{proj}#{iid}"
            work_item_source_id = context
        elif noteable_type == "MergeRequest" and payload.get("merge_request"):
            iid = payload["merge_request"].get("iid")
            proj = project.get("path_with_namespace", "")
            context = f"{proj}!{iid}"
            work_item_source_id = context

        result.interaction_events.append({
            "source": "gitlab",
            "source_id": str(note.get("id", entity_id)),
            "event_type": "comment",
            "channel_or_context": context,
            "author_source": "gitlab",
            "author_source_id": str(user.get("id", "")) if user else None,
            "body": note.get("note", ""),
            "work_item_source_id": work_item_source_id,
            "occurred_at": note.get("created_at"),
            "extra": {
                "noteable_type": noteable_type,
                "web_url": note.get("url"),
                "system": note.get("system", False),
            },
        })
        return result

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _map_milestone_state(state: str | None) -> str:
        if not state:
            return "future"
        return {"active": "active", "closed": "closed"}.get(state.lower(), "future")

    @staticmethod
    def _extract_priority_from_labels(labels: list[str]) -> str | None:
        for label in labels:
            lower = label.lower()
            if lower.startswith("priority::"):
                prio = lower.split("::", 1)[1]
                return BaseMapper._normalize_priority(prio)
        return None

    @staticmethod
    def _extract_points_from_labels(labels: list[str]) -> float | None:
        for label in labels:
            match = re.match(r"^(?:points?|sp)[:\s]*(\d+(?:\.\d+)?)$", label, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    @staticmethod
    def _extract_type_from_labels(labels: list[str]) -> str:
        for label in labels:
            lower = label.lower()
            if lower in ("bug", "defect"):
                return "bug"
            if lower in ("epic",):
                return "epic"
            if lower in ("story", "feature"):
                return "story"
        return "task"
