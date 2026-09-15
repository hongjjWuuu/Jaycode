"""Explicit persistence checks and opt-in migration utilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.persistence.postgres_store import PostgresTaskStore
from app.persistence.sqlite_store import task_store


def check() -> dict[str, object]:
    if settings.jaycode_persistence_store.lower() not in {"sqlite", "postgres"}:
        raise ValueError("JAYCODE_PERSISTENCE_STORE must be sqlite or postgres")
    store = settings.jaycode_persistence_store.lower()
    if store == "postgres":
        if not settings.database_url:
            raise ValueError("DATABASE_URL is required for postgres persistence")
        postgres = PostgresTaskStore(settings.database_url)
        with postgres.connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"configured_store": store, "postgres_reachable": True, "migration": "not_run"}
    with task_store._connect() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"configured_store": store, "sqlite_readable": True, "migration": "not_run"}


def export_sqlite(destination: Path) -> None:
    """Export a read-only SQLite snapshot as JSON; never deletes source data."""
    tables = ["agent_task", "agent_task_event", "agent_task_artifact", "security_audit_log"]
    payload: dict[str, object] = {"format": "jaycode-sqlite-export-v1", "tables": {}}
    with task_store._connect() as conn:
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            payload["tables"][table] = [dict(row) for row in rows]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Jaycode persistence safety checks")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--export-sqlite", type=Path)
    parser.add_argument("--import-postgres", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.export_sqlite:
        export_sqlite(args.export_sqlite)
        print(json.dumps({"exported": str(args.export_sqlite)}, ensure_ascii=False))
        return 0
    if args.verify:
        print(json.dumps({"verified": check(), "note": "Record-set verification requires an explicit target export."}, ensure_ascii=False))
        return 0
    if args.import_postgres:
        raise SystemExit("Import is intentionally not automatic; review the export and run an approved migration procedure.")
    print(json.dumps(check(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
