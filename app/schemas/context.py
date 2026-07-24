from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import DataSource


class SourceMetadata(BaseModel):
    type: str
    reference: str | None = None
    verified_at: date | None = None


class CampusLocation(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str
    longitude: float | None = None
    latitude: float | None = None
    zone: str | None = None
    is_outdoor: bool = False
    source: SourceMetadata


class TravelEstimate(BaseModel):
    origin_id: str
    destination_id: str
    mode: str = "walk"
    distance_m: int | None = Field(default=None, ge=0)
    duration_min: int = Field(ge=0, le=240)
    base_duration_min: int | None = Field(default=None, ge=0, le=240)
    congestion_delay_min: int = Field(default=0, ge=0, le=120)
    source: DataSource
    confidence: float = Field(ge=0, le=1)
    fetched_at: datetime | None = None
    warning: str | None = None


class CongestionWindow(BaseModel):
    start_at: datetime
    end_at: datetime
    duration_multiplier: float = Field(default=1.25, ge=1, le=3)
    minimum_extra_min: int = Field(default=3, ge=0, le=30)
    source: DataSource = DataSource.STRUCTURED

    @model_validator(mode="after")
    def validate_window(self) -> "CongestionWindow":
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("congestion window datetimes must include timezone")
        if self.end_at <= self.start_at:
            raise ValueError("congestion window end must be after start")
        return self


class WeatherContext(BaseModel):
    date: date
    period: str
    condition: str | None = None
    temperature_c: float | None = None
    rain_probability: float | None = Field(default=None, ge=0, le=1)
    risk_start_at: datetime | None = None
    source: DataSource
    fetched_at: datetime | None = None
    is_stale: bool = False


class RetrievedFact(BaseModel):
    id: str
    content: str
    applies_to: list[str] = Field(default_factory=list)
    priority: int = 0
    source: DataSource
    source_ref: str | None = None
    verified_at: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
