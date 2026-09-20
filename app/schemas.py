"""Request/response schemas. Validation errors surface as HTTP 422."""
from __future__ import annotations

from datetime import date, time
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator
from zoneinfo import ZoneInfo

from .core import MAX_RANGE_DAYS, GapStrategy, FoldStrategy

# Monday=0 ... Sunday=6, matching datetime.date.weekday().
Weekday = Annotated[int, Field(ge=0, le=6)]


class ExpandRequest(BaseModel):
    timezone: str = Field(description="IANA time zone name, e.g. America/New_York")
    start_date: date
    end_date: date
    weekdays: Annotated[set[Weekday], Field(min_length=1)] = Field(
        description="Days of week to include; 0=Monday ... 6=Sunday"
    )
    local_time: time = Field(description="Local wall-clock time, e.g. 02:30")
    gap_strategy: GapStrategy = GapStrategy.skip
    fold_strategy: FoldStrategy = FoldStrategy.first

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:  # ZoneInfoNotFoundError, ValueError, OSError
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value

    @model_validator(mode="after")
    def date_range_must_be_valid(self) -> "ExpandRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        if (self.end_date - self.start_date).days > MAX_RANGE_DAYS:
            raise ValueError(f"date range must not exceed {MAX_RANGE_DAYS} days")
        return self


class InstanceOut(BaseModel):
    local: str = Field(description="Local wall-clock time actually scheduled, ISO 8601")
    offset: str = Field(description="UTC offset in effect, e.g. -04:00")
    utc: str = Field(description="The instant in UTC, ISO 8601 with Z suffix")
    reason: str = Field(
        description="normal | gap_shift_forward | fold_first | fold_second"
    )


class ExpandResponse(BaseModel):
    timezone: str
    count: int
    instances: list[InstanceOut]
