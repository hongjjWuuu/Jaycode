"""Explicit persistence checks and opt-in migration utilities."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.persistence.postgres_store import PostgresTaskStore
from app.persistence.sqlite_path import resolve_sqlite_path


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$bytes_base64": base64.b64encode(value).decode("ascii")}
    return value


def sqlite_manifest(database_path: Path) -> dict[str, Any]:
    """Return deterministic counts, primary-key digests, and content hashes."""
    connection = sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity}")
        table_names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        tables: dict[str, Any] = {}
        for table in table_names:
            quoted_table = table.replace('"', '""')
            cursor = connection.execute(f'SELECT * FROM "{quoted_table}"')
            column_names = [str(column[0]) for column in cursor.description or ()]
            primary_key = [
                str(row[1])
                for row in sorted(
                    connection.execute(f'PRAGMA table_info("{quoted_table}")').fetchall(),
                    key=lambda item: int(item[5]) if item[5] else 2**31,
                )
                if int(row[5]) > 0
            ]
            row_hashes: list[str] = []
            primary_key_hashes: list[str] = []
            for values in cursor.fetchall():
                row = {name: _json_value(value) for name, value in zip(column_names, values, strict=True)}
                serialized = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                row_hashes.append(hashlib.sha256(serialized.encode("utf-8")).hexdigest())
                if primary_key:
                    key_json = json.dumps([row[name] for name in primary_key], ensure_ascii=False, separators=(",", ":"))
                    primary_key_hashes.append(hashlib.sha256(key_json.encode("utf-8")).hexdigest())
            tables[table] = {
                "row_count": len(row_hashes),
                "primary_key_columns": primary_key,
                "primary_key_sha256": _hash_sorted(primary_key_hashes) if primary_key else None,
                "rows_sha256": _hash_sorted(row_hashes),
            }
        return {"format": "jaycode-sqlite-manifest-v1", "integrity": integrity, "tables": tables}
    finally:
        connection.close()


def _hash_sorted(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def backup_sqlite(destination: Path, source: Path | None = None) -> dict[str, Any]:
    """Create a consistent, non-overwriting SQLite backup and adjacent manifest."""
    source_path = source or resolve_sqlite_path()
    destination = destination.resolve()
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    if destination.exists() or manifest_path.exists():
        raise FileExistsError("Backup or manifest destination already exists; refusing to overwrite.")
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source does not exist: {source_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite backup integrity check failed: {integrity}")
    except Exception:
        dst.close()
        src.close()
        destination.unlink(missing_ok=True)
        raise
    else:
        dst.close()
        src.close()
    try:
        manifest = sqlite_manifest(destination)
        with manifest_path.open("x", encoding="utf-8") as manifest_file:
            manifest_file.write(json.dumps(manifest, ensure_ascii=False, indent=2))
            manifest_file.write("\n")
    except Exception:
        manifest_path.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    return {"backup": str(destination), "manifest": str(manifest_path), "tables": len(manifest["tables"]), "integrity": manifest["integrity"]}


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
    source_path = resolve_sqlite_path()
    with sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True) as conn:
        conn.execute("SELECT 1").fetchone()
    return {"configured_store": store, "sqlite_readable": True, "migration": "not_run"}


def export_sqlite(destination: Path, source: Path | None = None) -> dict[str, Any]:
    """Export every user table from a read-only SQLite snapshot without overwrite."""
    source_path = source or resolve_sqlite_path()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Export destination already exists: {destination}")
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source does not exist: {source_path}")
    manifest = sqlite_manifest(source_path)
    connection = sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables: dict[str, Any] = {}
        for table in manifest["tables"]:
            quoted = table.replace('"', '""')
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            rows = connection.execute(f'SELECT * FROM "{quoted}"').fetchall()
            tables[table] = {
                "create_sql": schema["sql"] if schema else None,
                "columns": [dict(row) for row in connection.execute(f'PRAGMA table_info("{quoted}")')],
                "rows": [
                    {key: _json_value(value) for key, value in dict(row).items()}
                    for row in rows
                ],
                "manifest": manifest["tables"][table],
            }
    finally:
        connection.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"format": "jaycode-sqlite-export-v2", "manifest": manifest, "tables": tables}
    with destination.open("x", encoding="utf-8") as export_file:
        export_file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        export_file.write("\n")
    return {"export": str(destination), "tables": len(tables), "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Jaycode persistence safety checks")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--export-sqlite", type=Path)
    parser.add_argument("--source-sqlite", type=Path, help="SQLite source file for export or verification")
    parser.add_argument("--backup-sqlite", type=Path, help="Create a consistent SQLite backup and hash manifest without overwriting files")
    parser.add_argument("--import-postgres", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.backup_sqlite:
        print(json.dumps(backup_sqlite(args.backup_sqlite), ensure_ascii=False))
        return 0
    if args.export_sqlite:
        result = export_sqlite(args.export_sqlite, args.source_sqlite)
        print(json.dumps(result, ensure_ascii=False))
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
