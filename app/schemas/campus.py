from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.context import CampusLocation


class CampusSelection(BaseModel):
    campus_id: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    display_name: str = Field(min_length=2, max_length=120)
    search_city: str = Field(default="", max_length=60)
    weather_adcode: str = Field(default="", max_length=12)
    longitude: float | None = Field(default=None, ge=70, le=140)
    latitude: float | None = Field(default=None, ge=0, le=60)
    locations: list[CampusLocation] = Field(
        default_factory=list,
        max_length=200,
    )

    @model_validator(mode="after")
    def validate_location_ownership(self) -> "CampusSelection":
        for location in self.locations:
            if location.campus_id not in (None, self.campus_id):
                raise ValueError("campus location belongs to another campus")
        return self


class CampusDiscoveryRequest(BaseModel):
    school_name: str = Field(min_length=2, max_length=120)
    city: str = Field(default="", max_length=60)
    radius_m: int = Field(default=1800, ge=300, le=5000)


class CampusDiscoveryResponse(BaseModel):
    campus: CampusSelection
    searched_categories: list[str]
    coverage_note: str
    source: str = "高德地点搜索"
