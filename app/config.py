from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


def _runtime_dir() -> Path:
    """Return a writable runtime directory for local and Vercel execution."""
    if os.getenv("VERCEL"):
        return Path("/tmp") / "yicheng-agent"
    return BASE_DIR / "runtime"


def _app_database_path() -> Path:
    return _runtime_dir() / "app.db"


def _checkpoint_database_path() -> Path:
    return _runtime_dir() / "checkpoints.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_timezone: str = "Asia/Shanghai"
    app_database_path: Path = Field(default_factory=_app_database_path)
    app_checkpoint_database_path: Path = Field(
        default_factory=_checkpoint_database_path
    )
    app_data_dir: Path = BASE_DIR / "data"
    app_demo_dir: Path = BASE_DIR / "fixtures"
    app_access_enabled: bool = False
    app_test_username: str = ""
    app_test_password: str = Field(default="", repr=False)
    app_auth_secret: str = Field(default="", repr=False)
    app_access_hours: int = Field(default=8, ge=1, le=72)
    # Keep API documentation private on the public site unless explicitly
    # enabled for local development or an authenticated maintenance window.
    app_docs_enabled: bool = False

    llm_enabled: bool = False
    llm_model: str = "qwen3.8-max"
    llm_fallback_models: str = (
        "deepseek-v4-flash-0731,glm-5.2-fast-preview,"
        "qwen3.7-flash-2026-07-15,qwen3.6-plus,"
        "qwen-plus-2025-12-01,glm-5.1,glm-5"
    )
    llm_base_url: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_enable_thinking: bool = False
    llm_render_enabled: bool = True
    llm_plan_render_enabled: bool = False
    llm_timeout_seconds: float = Field(default=20, ge=1, le=120)

    live_route_enabled: bool = False
    route_api_base_url: str = ""
    route_api_key: str = Field(default="", repr=False)
    route_timeout_seconds: float = Field(default=3, ge=0.5, le=30)

    live_weather_enabled: bool = False
    weather_api_base_url: str = ""
    weather_api_key: str = Field(default="", repr=False)
    weather_timeout_seconds: float = Field(default=3, ge=0.5, le=30)
    weather_city_adcode: str = ""

    @property
    def llm_models(self) -> list[str]:
        """Return the configured model chain without duplicate names."""
        models: list[str] = []
        for raw_name in (
            self.llm_model,
            *self.llm_fallback_models.split(","),
        ):
            name = raw_name.strip()
            if name and name not in models:
                models.append(name)
        return models

    def ensure_runtime_dirs(self) -> None:
        self.app_database_path.parent.mkdir(parents=True, exist_ok=True)
        self.app_checkpoint_database_path.parent.mkdir(
            parents=True, exist_ok=True
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_dirs()
    return settings
