from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import Intent
from app.schemas.task import Task, UserPreferences


class UnderstandResult(BaseModel):
    intent: Intent
    requested_date: date
    tasks: list[Task]
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    clarifications: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1, ge=0, le=1)

