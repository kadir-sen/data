"""WorkItem request / response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class WorkItemBase(BaseModel):
    source: str = Field(..., max_length=64, examples=["jira"])
    source_id: str = Field(..., max_length=256, examples=["PROJ-123"])
    title: str = Field(..., max_length=1024, examples=["Implement login page"])
    description: str | None = None
    item_type: str = Field(
        "task",
        pattern="^(epic|story|task|bug|subtask)$",
        examples=["story"],
    )
    status: str = Field(
        "open",
        pattern="^(open|in_progress|review|done|closed)$",
        examples=["in_progress"],
    )
    priority: str | None = Field(None, pattern="^(critical|high|medium|low)$", examples=["high"])
    story_points: float | None = Field(None, ge=0, examples=[5.0])
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None
    sprint_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    labels: list[str] | None = None
    extra: dict | None = None


class WorkItemCreate(WorkItemBase):
    pass


class WorkItemUpdate(BaseModel):
    title: str | None = Field(None, max_length=1024)
    status: str | None = Field(None, pattern="^(open|in_progress|review|done|closed)$")
    priority: str | None = Field(None, pattern="^(critical|high|medium|low)$")
    story_points: float | None = None
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None
    sprint_id: uuid.UUID | None = None
    labels: list[str] | None = None
    extra: dict | None = None


class WorkItemRead(WorkItemBase):
    id: uuid.UUID
    resolved_at: datetime | None = None
    changelog: list | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
