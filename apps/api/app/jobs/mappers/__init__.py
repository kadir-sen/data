"""Source-specific mappers: raw_event payload -> canonical tables."""

from app.jobs.mappers.base import BaseMapper, MapperResult
from app.jobs.mappers.confluence import ConfluenceMapper
from app.jobs.mappers.gitlab import GitLabMapper
from app.jobs.mappers.google_meet import GoogleMeetMapper
from app.jobs.mappers.jira import JiraMapper
from app.jobs.mappers.notion import NotionMapper
from app.jobs.mappers.slack import SlackMapper

MAPPER_REGISTRY: dict[str, type[BaseMapper]] = {
    "jira": JiraMapper,
    "gitlab": GitLabMapper,
    "notion": NotionMapper,
    "slack": SlackMapper,
    "confluence": ConfluenceMapper,
    "google_meet": GoogleMeetMapper,
}

__all__ = [
    "BaseMapper",
    "MapperResult",
    "MAPPER_REGISTRY",
    "JiraMapper",
    "GitLabMapper",
    "NotionMapper",
    "SlackMapper",
    "ConfluenceMapper",
    "GoogleMeetMapper",
]
