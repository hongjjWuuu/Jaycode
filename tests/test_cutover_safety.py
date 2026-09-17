from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.persistence.cutover import CutoverConfigurationError, validate_cutover_urls
from app.persistence.migrate import (
    CUTOVER_DATABASE_NAME,
    CUTOVER_TARGET_ENV,
    _assert_cutover_backup_source,
    _target_url,
    sqlite_manifest,
)


def test_cutover_urls_require_same_loopback_maintenance_pair() -> None:
    result = validate_cutover_urls(
        "postgresql://user:secret@localhost:5432/postgres",
        "postgresql://user:secret@127.0.0.1:5432/jayagent_studio",
    )
    assert result == {"host": "127.0.0.1", "port": 5432, "database": "jayagent_studio"}


@pytest.mark.parametrize(
    ("admin_url", "target_url"),
    [
        ("postgresql://localhost/jayagent_studio", "postgresql://localhost/jayagent_studio"),
        ("postgresql://localhost/postgres", "postgresql://db.example/jayagent_studio"),
        ("postgresql://localhost/postgres", "postgresql://localhost/dev_agent_studio"),
        ("postgresql://localhost/postgres", "https://localhost/jayagent_studio"),
    ],
)
def test_cutover_urls_reject_wrong_admin_or_target(admin_url: str, target_url: str) -> None:
    with pytest.raises(CutoverConfigurationError):
        validate_cutover_urls(admin_url, target_url)


def test_production_target_requires_dedicated_env_and_exact_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CUTOVER_TARGET_ENV, "postgresql://localhost/jayagent_studio")
    assert _target_url(CUTOVER_TARGET_ENV, production_cutover=True).endswith(f"/{CUTOVER_DATABASE_NAME}")
    with pytest.raises(ValueError, match="requires JAYCODE_CUTOVER_DATABASE_URL"):
        _target_url("JAYCODE_MIGRATION_TARGET_URL", production_cutover=True)


def test_cutover_source_requires_verified_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    backup_dir = tmp_path / "data" / "backups"
    backup_dir.mkdir(parents=True)
    backup = backup_dir / "dev_agent_studio-pre-postgres-20260916T000000Z.db"
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE sample(id TEXT PRIMARY KEY)")
    with pytest.raises(ValueError, match="manifest"):
        _assert_cutover_backup_source(backup)
    manifest = backup.with_suffix(".db.manifest.json")
    manifest.write_text(json.dumps(sqlite_manifest(backup)), encoding="utf-8")
    _assert_cutover_backup_source(backup)
    manifest.write_text(json.dumps({"format": "not-a-real-manifest"}), encoding="utf-8")
    with pytest.raises(ValueError, match="no longer matches"):
        _assert_cutover_backup_source(backup)
