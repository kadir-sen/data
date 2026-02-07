"""EffortLog request / response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EffortLogBase(BaseModel):
    day: date = Field(..., examples=["2025-01-15"])
    hours: float = Field(..., gt=0, le=24, examples=[6.5])
    category: str = Field(
        "development",
        pattern="^(development|review|meeting|support|admin|other)$",
        examples=["development"],
    )
    description: str | None = Field(None, examples=["Worked on auth module"])
    work_item_id: uuid.UUID | None = None
    planned_hours: float | None = Field(None, gt=0, le=24, examples=[8.0])
    source: str = Field(
        "manual",
        pattern="^(manual|jira_tempo|gitlab_time|csv)$",
        examples=["manual"],
    )
    extra: dict | None = None


class EffortLogCreate(EffortLogBase):
    """POST body – person_id is set from the authenticated user's linked Person."""
    pass


class EffortLogUpdate(BaseModel):
    hours: float | None = Field(None, gt=0, le=24)
    category: str | None = Field(None, pattern="^(development|review|meeting|support|admin|other)$")
    description: str | None = None
    planned_hours: float | None = Field(None, gt=0, le=24)
    extra: dict | None = None


class EffortLogRead(EffortLogBase):
    id: uuid.UUID
    person_id: uuid.UUID
    locked: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class DaySummary(BaseModel):
    """Aggregated effort for a single day."""
    day: date
    total_hours: float
    planned_hours: float | None = None
    by_category: dict[str, float] = Field(default_factory=dict)


class TeamMemberEffort(BaseModel):
    """Effort summary for one team member."""
    person_id: uuid.UUID
    display_name: str
    total_hours: float
    by_category: dict[str, float] = Field(default_factory=dict)


class TeamEffortResponse(BaseModel):
    """Aggregate team effort within a date range."""
    team_id: str
    from_date: date
    to_date: date
    total_hours: float
    by_category: dict[str, float] = Field(default_factory=dict)
    by_day: list[DaySummary] = Field(default_factory=list)
    members: list[TeamMemberEffort] = Field(default_factory=list)


class SprintEffortResponse(BaseModel):
    """Effort vs delivered work for a sprint."""
    sprint_id: uuid.UUID
    sprint_name: str
    total_effort_hours: float
    by_category: dict[str, float] = Field(default_factory=dict)
    total_story_points: float | None = None
    items_done: int = 0
    items_total: int = 0
