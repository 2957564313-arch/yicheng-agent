from __future__ import annotations

from datetime import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Intent(StrEnum):
    PLAN = "plan"
    REPLAN = "replan"
    WEATHER_CHECK = "weather_check"
    QUERY = "query"


class TaskFlexibility(StrEnum):
    FIXED = "fixed"
    MOVABLE = "movable"
    LOCKED = "locked"


class TransportMode(StrEnum):
    WALK = "walk"
    BICYCLE = "bicycle"
    ELECTROBIKE = "electrobike"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INFEASIBLE = "infeasible"


class DataSource(StrEnum):
    USER = "user"
    STRUCTURED = "structured"
    LIVE_API = "live_api"
    CACHE = "cache"
    RAG = "rag"
    ESTIMATED = "estimated"
    DEMO_FIXTURE = "demo_fixture"
    UNKNOWN = "unknown"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class TimeWindow(BaseModel):
    start: time
    end: time

    @model_validator(mode="after")
    def validate_order(self) -> "TimeWindow":
        if self.end <= self.start:
            raise ValueError("time window end must be after start")
        return self


class Issue(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    severity: IssueSeverity
    message: str = Field(min_length=1, max_length=500)
    task_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool = True
