from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from postgres_test_config import isolated_postgres_url

from app.persistence.memory_store import SQLiteMemoryStore
from app.persistence.migration_mapping import TABLE_MAPPINGS
from app.persistence.migrate import import_postgres, verify_postgres
from app.persistence.postgres_store import PostgresTaskStore
from app.persistence.rag_store import SQLiteRagStore
from app.persistence.sqlite_store import SQLiteTaskStore


pytestmark = pytest.mark.postgres
DATABASE_URL = isolated_postgres_url()
TARGET_ENV = "JAYCODE_MIGRATION_TARGET_URL"


@pytest.fixture(autouse=True)
def empty_rehearsal_target(monkeypatch: pytest.MonkeyPatch) -> None:
    if not DATABASE_URL:
        return
    monkeypatch.setenv(TARGET_ENV, DATABASE_URL)
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    with store.connection() as connection:
        from psycopg import sql

        connection.execute(
            sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(", ").join(sql.Identifier(mapping.target_table) for mapping in TABLE_MAPPINGS.values())
            )
        )
        connection.execute("CREATE TABLE IF NOT EXISTS jaycode_migration_import (source_fingerprint TEXT PRIMARY KEY, mapping_version TEXT NOT NULL, imported_at TIMESTAMPTZ NOT NULL DEFAULT now(), verification_json JSONB NOT NULL DEFAULT '{}'::jsonb)")
        connection.execute("DELETE FROM jaycode_migration_import")


def _source_database(path: Path, *, invalid_audit_json: bool = False) -> Path:
    task_store = SQLiteTaskStore(path)
    SQLiteMemoryStore(path)
    SQLiteRagStore(path)
    suffix = uuid4().hex
    task_store.create_task(
        f"migration-task-{suffix}",
        "migration rehearsal",
        None,
        "completed",
        {"idempotency_key": f"migration-{suffix}"},
        {"source": "synthetic"},
    )
    with task_store._connect() as connection:
        connection.execute(
            """INSERT INTO security_audit_log(
                audit_id,request_id,actor_id,role,action,resource_type,resource_id,status,metadata_json,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                f"migration-audit-{suffix}",
                f"request-{suffix}",
                "migration-test",
                "admin",
                "migration_rehearsal",
                "test",
                suffix,
                "completed",
                "{invalid" if invalid_audit_json else '{"safe":true}',
                "2026-09-16T00:00:00+08:00",
            ),
        )
    return path


def test_rehearsal_import_verify_and_repeat_rejection(tmp_path: Path) -> None:
    if not DATABASE_URL:
        pytest.skip("set JAYCODE_TEST_DATABASE_URL to an isolated local test database")
    source = _source_database(tmp_path / "source.sqlite3")

    imported = import_postgres(source, TARGET_ENV)
    assert imported["tables"]["agent_task"]["row_count"] == 1
    assert verify_postgres(source, TARGET_ENV)["tables"]["security_audit_log"]["row_count"] == 1
    with pytest.raises(ValueError, match="contains business data|ledger"):
        import_postgres(source, TARGET_ENV)


def test_rehearsal_rejects_unknown_schema_before_target_write(tmp_path: Path) -> None:
    if not DATABASE_URL:
        pytest.skip("set JAYCODE_TEST_DATABASE_URL to an isolated local test database")
    source = _source_database(tmp_path / "unknown.sqlite3")
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE unrecognised_source_table(id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO unrecognised_source_table VALUES ('unexpected')")
    with pytest.raises(ValueError, match="unmapped tables"):
        import_postgres(source, TARGET_ENV)


def test_rehearsal_rolls_back_on_invalid_json(tmp_path: Path) -> None:
    if not DATABASE_URL:
        pytest.skip("set JAYCODE_TEST_DATABASE_URL to an isolated local test database")
    source = _source_database(tmp_path / "invalid.sqlite3", invalid_audit_json=True)
    with pytest.raises(ValueError, match="invalid JSON"):
        import_postgres(source, TARGET_ENV)
    store = PostgresTaskStore(DATABASE_URL)
    with store.connection() as connection:
        assert connection.execute("SELECT count(*) AS count FROM agent_task").fetchone()["count"] == 0
        assert connection.execute("SELECT count(*) AS count FROM jaycode_migration_import").fetchone()["count"] == 0
