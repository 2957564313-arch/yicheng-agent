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

    llm_enabled: bool = False
    llm_model: str = "qwen3.6-flash"
    llm_base_url: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_enable_thinking: bool = False
    llm_render_enabled: bool = True
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
