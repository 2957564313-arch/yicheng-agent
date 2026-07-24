from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_vercel_uses_writable_tmp_storage(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")

    settings = Settings(_env_file=None)

    assert settings.app_database_path == Path(
        "/tmp/yicheng-agent/app.db"
    )
    assert settings.app_checkpoint_database_path == Path(
        "/tmp/yicheng-agent/checkpoints.db"
    )
