"""Person response schema (read-only via this API)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PersonRead(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str | None = None
    role: str = Field(..., examples=["member"])
    team: str | None = None
    source_ids: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
