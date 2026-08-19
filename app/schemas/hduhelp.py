from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.schemas.timetable import TimetableImportResponse


class HduHelpTerm(BaseModel):
    school_year: str = Field(min_length=4, max_length=20)
    semester: int = Field(ge=1, le=3)
    raw_entry_count: int = Field(default=0, ge=0)


class HduHelpConnectRequest(BaseModel):
    token: SecretStr

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().strip()) < 20:
            raise ValueError("个人访问令牌格式不正确")
        return value


class HduHelpConnectionStatus(BaseModel):
    connected: bool = False
    provider: str = "hduhelp"
    display_name: str | None = None
    available_terms: list[HduHelpTerm] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    last_error: str | None = None
    synced_counts: dict[str, int] = Field(default_factory=dict)


class HduHelpSyncRequest(BaseModel):
    school_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    semester: int = Field(ge=1, le=3)
    name: str = Field(default="杭电助手课表", min_length=1, max_length=80)


class HduHelpSyncResponse(TimetableImportResponse):
    school_year: str
    semester: int
    synced_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
