"""Sprint request / response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class SprintBase(BaseModel):
    name: str = Field(..., max_length=256, examples=["Sprint 42"])
    source: str = Field(..., max_length=64, examples=["jira"])
    source_id: str = Field(..., max_length=256, examples=["12345"])
    board_or_project: str | None = Field(None, max_length=256, examples=["PROJ"])
    status: str = Field("future", pattern="^(future|active|closed)$", examples=["active"])
    start_date: date | None = Field(None, examples=["2025-01-06"])
    end_date: date | None = Field(None, examples=["2025-01-17"])
    goal: str | None = Field(None, max_length=1024, examples=["Ship auth module"])
    extra: dict | None = None


class SprintCreate(SprintBase):
    pass


class SprintUpdate(BaseModel):
    name: str | None = Field(None, max_length=256)
    status: str | None = Field(None, pattern="^(future|active|closed)$")
    start_date: date | None = None
    end_date: date | None = None
    goal: str | None = None
    extra: dict | None = None


class SprintRead(SprintBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    work_item_count: int = Field(0, description="Number of work items in this sprint")

    model_config = {"from_attributes": True}
