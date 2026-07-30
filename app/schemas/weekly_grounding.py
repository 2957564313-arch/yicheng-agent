from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import DataSource, Issue
from app.schemas.plan import Plan


class WeeklyDailyGroundingEvidence(BaseModel):
    """Machine-readable evidence used to validate a materialised day."""

    route_sources: list[DataSource] = Field(default_factory=list)
    weather_sources: list[DataSource] = Field(default_factory=list)
    opening_rule_location_ids: list[str] = Field(default_factory=list)
    timetable_task_count: int = Field(default=0, ge=0)
    route_pair_count: int = Field(default=0, ge=0)
    weather_enforced: bool = False


class WeeklyDailyGroundingResponse(BaseModel):
    status: Literal[
        "grounded",
        "already_grounded",
        "infeasible",
        "empty",
    ]
    weekly_plan_id: str = Field(min_length=1, max_length=80)
    date: date
    allocation_ids: list[str] = Field(default_factory=list)
    plan: Plan | None = None
    issues: list[Issue] = Field(default_factory=list)
    evidence: WeeklyDailyGroundingEvidence = Field(
        default_factory=WeeklyDailyGroundingEvidence
    )
