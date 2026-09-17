from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from postgres_test_config import isolated_postgres_url

from app.persistence.memory_store import SQLiteMemoryStore
from app.persistence.migrate import import_postgres, verify_postgres
from app.persistence.migration_mapping import TABLE_MAPPINGS
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
            """INSERT INTO agent_task_node_state(
                task_id,node_id,state,attempt,error_message,output_json,started_at,finished_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f"migration-task-{suffix}", "migration-node", "completed", 1, None,
                '{"safe":true}', "2026-09-16T00:00:00+08:00", "2026-09-16T00:00:01+08:00",
                "2026-09-16T00:00:01+08:00",
            ),
        )
        connection.execute(
            "INSERT INTO schema_migration(version,name,applied_at) VALUES (?,?,?)",
            (999, "migration-rehearsal", "2026-09-16T00:00:00+08:00"),
        )
        connection.execute(
            """INSERT INTO benchmark_comparison(
                comparison_id,current_run_id,baseline_run_id,regression_status,
                threshold_json,delta_json,created_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                f"comparison-{suffix}",
                f"run-{suffix}",
                None,
                "pass",
                '{"recall_at_8":0.01}',
                '{"recall_at_8":0.0}',
                "2026-09-16T00:00:00+08:00",
            ),
        )
        connection.execute(
            """INSERT INTO marketplace_install_snapshot(
                snapshot_id,package_id,package_type,manifest_json,state_json,created_at
            ) VALUES (?,?,?,?,?,?)""",
            (
                f"snapshot-{suffix}",
                f"package-{suffix}",
                "skill",
                '{"name":"synthetic"}',
                '{"installed":true}',
                "2026-09-16T00:00:00+08:00",
            ),
        )
        connection.execute(
            """INSERT INTO platform_version(
                version_id,object_type,object_id,version,status,manifest_json,created_by,created_at,activated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f"version-{suffix}",
                "skill",
                f"package-{suffix}",
                "1.0.0",
                "active",
                '{"safe":true}',
                "migration-test",
                "2026-09-16T00:00:00+08:00",
                "2026-09-16T00:00:01+08:00",
            ),
        )
        connection.execute(
            """INSERT INTO platform_approval(
                approval_id,object_type,object_id,version_id,actor_id,decision,reason,created_at
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                f"approval-{suffix}",
                "skill",
                f"package-{suffix}",
                f"version-{suffix}",
                "migration-test",
                "approved",
                "synthetic",
                "2026-09-16T00:00:00+08:00",
            ),
        )
        connection.execute(
            """INSERT INTO platform_query(
                query_id,query_type,actor_id,task_id,input_json,result_json,score_json,created_at
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                f"query-{suffix}",
                "search",
                "migration-test",
                f"migration-task-{suffix}",
                '{"query":"synthetic"}',
                '{"items":[]}',
                '{"score":1.0}',
                "2026-09-16T00:00:00+08:00",
            ),
        )
        connection.execute(
            """INSERT INTO rag_evaluation_run(
                run_id,collection,actor_id,case_count,hit_count,recall_at_8,mrr,result_json,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f"rag-eval-{suffix}",
                "default",
                "migration-test",
                1,
                1,
                1.0,
                1.0,
                '{"case_ids":[]}',
                "2026-09-16T00:00:00+08:00",
            ),
        )
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
    assert imported["tables"]["agent_task_node_state"]["row_count"] == 1
    assert imported["tables"]["benchmark_comparison"]["row_count"] == 1
    assert imported["tables"]["marketplace_install_snapshot"]["row_count"] == 1
    assert imported["tables"]["platform_approval"]["row_count"] == 1
    assert imported["tables"]["platform_query"]["row_count"] == 1
    assert imported["tables"]["platform_version"]["row_count"] == 1
    assert imported["tables"]["rag_evaluation_run"]["row_count"] == 1
    assert imported["tables"]["schema_migration"]["row_count"] == 1
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
