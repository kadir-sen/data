"""Report request / response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class ReportBase(BaseModel):
    period: str = Field(..., pattern="^(daily|weekly|monthly)$", examples=["weekly"])
    period_start: date = Field(..., examples=["2025-01-06"])
    period_end: date = Field(..., examples=["2025-01-12"])
    title: str = Field(..., max_length=512, examples=["Week 2 Sprint Report"])
    summary: str | None = Field(None, examples=["Velocity increased by 15%"])
    metrics: dict = Field(
        default_factory=dict,
        examples=[{"velocity": 42, "burndown_remaining": 18, "effort_total_hours": 320}],
    )
    extra: dict | None = None


class ReportCreate(ReportBase):
    pass


class ReportUpdate(BaseModel):
    title: str | None = Field(None, max_length=512)
    summary: str | None = None
    metrics: dict | None = None
    extra: dict | None = None


class ReportRead(ReportBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
