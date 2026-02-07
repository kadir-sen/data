"""Incremental sync connectors – pull data from external APIs into raw_event."""

from app.jobs.sync.base import BaseConnector, SyncResult
from app.jobs.sync.jira import JiraConnector
from app.jobs.sync.gitlab import GitLabConnector
from app.jobs.sync.confluence import ConfluenceConnector
from app.jobs.sync.slack import SlackConnector
from app.jobs.sync.notion import NotionConnector
from app.jobs.sync.google_meet import GoogleMeetConnector

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "jira": JiraConnector,
    "gitlab": GitLabConnector,
    "confluence": ConfluenceConnector,
    "slack": SlackConnector,
    "notion": NotionConnector,
    "google_meet": GoogleMeetConnector,
}

__all__ = [
    "BaseConnector",
    "SyncResult",
    "CONNECTOR_REGISTRY",
    "JiraConnector",
    "GitLabConnector",
    "ConfluenceConnector",
    "SlackConnector",
    "NotionConnector",
    "GoogleMeetConnector",
]
