"""Shared pagination, sorting, and response wrappers."""

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    offset: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(50, ge=1, le=200, description="Max items to return")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope for paginated list endpoints."""

    items: list[T]
    total: int = Field(..., description="Total matching records")
    offset: int
    limit: int
