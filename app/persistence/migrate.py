"""Explicit persistence checks and opt-in migration utilities."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings
from app.persistence.migration_mapping import MAPPING_VERSION, TABLE_MAPPINGS
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


def _target_url(environment_name: str) -> str:
    import os

    if not environment_name or environment_name == "DATABASE_URL":
        raise ValueError("A dedicated target URL environment variable is required; DATABASE_URL is not accepted.")
    value = os.getenv(environment_name, "").strip()
    if not value:
        raise ValueError(f"Set {environment_name} to an isolated PostgreSQL target URL.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("Migration target must be a PostgreSQL URL.")
    if (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Stage-four migration rehearsal is restricted to loopback PostgreSQL targets.")
    if not parsed.path.lstrip("/").startswith("jaycode_test_"):
        raise ValueError("Stage-four migration rehearsal requires a random jaycode_test_* target database.")
    return value


def _sqlite_table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    escaped = table.replace('"', '""')
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{escaped}")')]


def _source_tables(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return _json_value(value)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith(("{", "[")):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return value
    return value


def _row_digest(row: dict[str, Any]) -> str:
    payload = json.dumps({key: _canonical(value) for key, value in sorted(row.items())}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _derived_value(table: str, column: str, source: dict[str, Any]) -> Any:
    stable = _row_digest(source)[:24]
    if column == "review_id":
        return f"migration_review_{stable}"
    if column == "event_seq" and table == "agent_task_event":
        return int(source.get("id") or 1)
    if column == "prompt_id":
        return f"migration_prompt_{stable}"
    if column == "result_id":
        return f"migration_result_{stable}"
    if column == "request_id":
        return str(source.get("request_id") or "")
    if column == "role":
        return str(source.get("role") or "unknown")
    if column == "actor_id":
        return str(source.get("actor_id") or "unknown")
    if column == "status":
        return "failed" if source.get("error_message") else "completed"
    if column == "model":
        return str(source.get("model") or "unknown")
    if column == "source_json":
        return {"url": source.get("source_url")} if source.get("source_url") else {}
    if column == "manifest_json":
        return dict(source)
    if column in {"definition_json", "metrics_json", "content_json", "token_usage", "quality_reasons", "input_schema"}:
        return {}
    if column == "dataset_version":
        config = _parse_json(source.get("config_json"), "config_json")
        return str(config.get("dataset_version") or "unspecified") if isinstance(config, dict) else "unspecified"
    if column == "result_json":
        return dict(source)
    if column == "name" and table == "llm_prompt_version":
        return str(source.get("agent") or "unknown")
    if column == "version" and table == "llm_prompt_version":
        return str(source.get("prompt_version") or "v1")
    if column == "version" and table == "plugin_marketplace_install":
        return str(source.get("version") or "unknown")
    if column == "template" and table == "llm_prompt_version":
        return str(source.get("system_suffix") or "")
    if column == "command" and table == "mcp_server_config":
        return str(source.get("command") or "")
    if column == "embedding":
        from app.core.config import settings as app_settings

        seed = hashlib.sha256(str(source.get("content") or source.get("chunk_id") or stable).encode("utf-8")).digest()
        values = [(seed[index % len(seed)] / 255.0) * 2 - 1 for index in range(app_settings.jaycode_embedding_dim)]
        return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
    if column == "embedding_source":
        return "migration_hash"
    if column == "document_version":
        return int(source.get("document_version") or 1)
    return None


def _parse_json(value: Any, column: str) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{column} must contain JSON text.")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{column} contains invalid JSON.") from exc


def _target_columns(connection: Any, table: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT column_name, data_type, udt_name, is_nullable, column_default
           FROM information_schema.columns WHERE table_schema='public' AND table_name=%s
           ORDER BY ordinal_position""",
        (table,),
    ).fetchall()
    return [dict(row) for row in rows]


def _mapped_row(table: str, source: dict[str, Any], target_columns: list[dict[str, Any]]) -> dict[str, Any]:
    mapping = TABLE_MAPPINGS[table]
    result: dict[str, Any] = {}
    source_names = set(source)
    for metadata in target_columns:
        target = str(metadata["column_name"])
        if target in mapping.generated_target_columns:
            continue
        source_name = mapping.aliases.get(target, target)
        if source_name in source_names:
            value = source[source_name]
            if value is None:
                derived = _derived_value(table, target, source)
                if derived is not None:
                    value = derived
        else:
            value = _derived_value(table, target, source)
        if value is None:
            if str(metadata["is_nullable"]) == "YES" or metadata["column_default"] is not None:
                continue
            raise ValueError(f"{table}.{target} is required but has no SQLite mapping.")
        if str(metadata["udt_name"]) == "jsonb":
            value = _parse_json(value, f"{table}.{source_name}") if source_name in source_names else value
        elif str(metadata["data_type"]) == "boolean":
            value = bool(value)
        elif str(metadata["data_type"]).startswith("timestamp"):
            from app.persistence.postgres_store import _postgres_timestamp

            value = _postgres_timestamp(value)
        result[target] = value
    mapped_source_columns = {
        mapping.aliases.get(str(metadata["column_name"]), str(metadata["column_name"]))
        for metadata in target_columns
    }
    ignored = mapping.ignored_source_columns | set(mapping.aliases.values())
    unmapped = source_names - ignored - mapped_source_columns
    # Columns missing from PostgreSQL are only acceptable when explicitly
    # represented by a target JSON manifest/result field.
    if unmapped and table not in {"skill_registry", "benchmark_result"}:
        raise ValueError(f"{table} has unmapped SQLite columns: {', '.join(sorted(unmapped))}")
    return result


def _migration_source_rows(source: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, list[str]]]:
    if not source.is_file():
        raise FileNotFoundError(f"SQLite source does not exist: {source}")
    connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = _source_tables(connection)
        unknown = sorted(set(tables) - set(TABLE_MAPPINGS))
        if unknown:
            raise ValueError(f"SQLite source contains unmapped tables: {', '.join(unknown)}")
        rows: dict[str, list[dict[str, Any]]] = {}
        columns: dict[str, list[str]] = {}
        for table in tables:
            escaped = table.replace('"', '""')
            columns[table] = _sqlite_table_columns(connection, table)
            rows[table] = [dict(row) for row in connection.execute(f'SELECT * FROM "{escaped}"')]
        return rows, sqlite_manifest(source), columns
    finally:
        connection.close()


def _assert_target_empty(connection: Any) -> None:
    from psycopg import sql

    for mapping in TABLE_MAPPINGS.values():
        count = connection.execute(sql.SQL("SELECT count(*) AS count FROM {}").format(sql.Identifier(mapping.target_table))).fetchone()["count"]
        if count:
            raise ValueError(f"PostgreSQL target contains business data in {mapping.target_table}; refusing import.")
    ledger = connection.execute("SELECT count(*) AS count FROM jaycode_migration_import").fetchone()["count"]
    if ledger:
        raise ValueError("PostgreSQL target already contains a migration import ledger entry; refusing repeat import.")


_DERIVED_TARGET_COLUMNS = {
    "review_id", "event_seq", "prompt_id", "result_id", "request_id", "role", "actor_id", "status",
    "model", "source_json", "manifest_json", "definition_json", "metrics_json", "content_json",
    "token_usage", "quality_reasons", "input_schema", "dataset_version", "result_json", "name", "version",
    "template", "command", "embedding", "embedding_source", "document_version",
}


def _validate_table_schema(table: str, source_columns: list[str], target_columns: list[dict[str, Any]]) -> None:
    mapping = TABLE_MAPPINGS[table]
    target_names = {str(item["column_name"]) for item in target_columns}
    accepted = (target_names | set(mapping.aliases.values()) | set(mapping.ignored_source_columns))
    if table in {"skill_registry", "benchmark_result"}:
        accepted.update(source_columns)
    unknown = set(source_columns) - accepted
    if unknown:
        raise ValueError(f"{table} has unmapped SQLite columns: {', '.join(sorted(unknown))}")
    for metadata in target_columns:
        target = str(metadata["column_name"])
        source_name = mapping.aliases.get(target, target)
        required = str(metadata["is_nullable"]) == "NO" and metadata["column_default"] is None
        if required and source_name not in source_columns and target not in _DERIVED_TARGET_COLUMNS:
            raise ValueError(f"{table}.{target} is required but has no SQLite mapping.")


def _init_import_ledger(connection: Any) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS jaycode_migration_import (
            source_fingerprint TEXT PRIMARY KEY, mapping_version TEXT NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(), verification_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
    )


def _source_fingerprint(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _insert_rows(connection: Any, table: str, rows: list[dict[str, Any]], target_columns: list[dict[str, Any]]) -> list[str]:
    from psycopg import sql

    hashes: list[str] = []
    column_types = {str(item["column_name"]): str(item["udt_name"]) for item in target_columns}
    for source in rows:
        row = _mapped_row(table, source, target_columns)
        columns = list(row)
        if not columns:
            continue
        values_sql = [sql.SQL("%s::jsonb") if column_types[column] == "jsonb" else sql.SQL("%s") for column in columns]
        values = [json.dumps(row[column], ensure_ascii=False) if column_types[column] == "jsonb" else row[column] for column in columns]
        connection.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(TABLE_MAPPINGS[table].target_table),
                sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                sql.SQL(", ").join(values_sql),
            ),
            values,
        )
        hashes.append(_row_digest(row))
    return hashes


def import_postgres(source: Path, target_url_env: str) -> dict[str, Any]:
    """Import one SQLite snapshot into a disposable PostgreSQL rehearsal database."""
    target_url = _target_url(target_url_env)
    source_rows, manifest, source_columns = _migration_source_rows(source)
    fingerprint = _source_fingerprint(manifest)
    store = PostgresTaskStore(target_url)
    store.init_full_schema()
    with store.connection() as connection:
        _init_import_ledger(connection)
        _assert_target_empty(connection)
        table_hashes: dict[str, list[str]] = {}
        for table, rows in source_rows.items():
            metadata = _target_columns(connection, TABLE_MAPPINGS[table].target_table)
            if not metadata:
                raise ValueError(f"PostgreSQL target is missing table {table}.")
            _validate_table_schema(table, source_columns[table], metadata)
            table_hashes[table] = _insert_rows(connection, table, rows, metadata)
        report = {
            "format": "jaycode-postgres-import-v1",
            "mapping_version": MAPPING_VERSION,
            "source_fingerprint": fingerprint,
            "tables": {
                table: {"row_count": len(values), "rows_sha256": _hash_sorted(values)}
                for table, values in table_hashes.items()
            },
        }
        connection.execute(
            "INSERT INTO jaycode_migration_import(source_fingerprint,mapping_version,verification_json) VALUES (%s,%s,%s::jsonb)",
            (fingerprint, MAPPING_VERSION, json.dumps(report, ensure_ascii=False)),
        )
    return report


def verify_postgres(source: Path, target_url_env: str) -> dict[str, Any]:
    """Compare mapped source rows against an imported disposable target database."""
    target_url = _target_url(target_url_env)
    source_rows, manifest, source_columns = _migration_source_rows(source)
    fingerprint = _source_fingerprint(manifest)
    store = PostgresTaskStore(target_url)
    report: dict[str, Any] = {"format": "jaycode-postgres-verify-v1", "source_fingerprint": fingerprint, "tables": {}}
    from psycopg import sql

    with store.connection() as connection:
        ledger = connection.execute("SELECT source_fingerprint FROM jaycode_migration_import WHERE source_fingerprint=%s", (fingerprint,)).fetchone()
        if not ledger:
            raise ValueError("Target has no matching import ledger entry.")
        for table, rows in source_rows.items():
            metadata = _target_columns(connection, TABLE_MAPPINGS[table].target_table)
            _validate_table_schema(table, source_columns[table], metadata)
            source_hashes = [_row_digest(_mapped_row(table, row, metadata)) for row in rows]
            columns = sorted({column for row in rows for column in _mapped_row(table, row, metadata)})
            if columns:
                selected = connection.execute(
                    sql.SQL("SELECT {} FROM {}").format(
                        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                        sql.Identifier(TABLE_MAPPINGS[table].target_table),
                    )
                ).fetchall()
                target_hashes = [_row_digest({column: row[column] for column in columns}) for row in selected]
            else:
                target_hashes = []
            expected = {"row_count": len(source_hashes), "rows_sha256": _hash_sorted(source_hashes)}
            actual = {"row_count": len(target_hashes), "rows_sha256": _hash_sorted(target_hashes)}
            if expected != actual:
                raise ValueError(f"Migration verification mismatch for {table}.")
            report["tables"][table] = expected
    return report


def check_rehearsal(source: Path, target_url_env: str) -> dict[str, Any]:
    """Read-only compatibility check for a pre-initialized rehearsal target."""
    target_url = _target_url(target_url_env)
    _rows, manifest, source_columns = _migration_source_rows(source)
    store = PostgresTaskStore(target_url)
    with store.connection() as connection:
        for table, columns in source_columns.items():
            metadata = _target_columns(connection, TABLE_MAPPINGS[table].target_table)
            if not metadata:
                raise ValueError(f"PostgreSQL target is missing table {table}.")
            _validate_table_schema(table, columns, metadata)
    return {
        "format": "jaycode-postgres-migration-check-v1",
        "mapping_version": MAPPING_VERSION,
        "source_fingerprint": _source_fingerprint(manifest),
        "tables": len(source_columns),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Jaycode persistence safety checks")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--export-sqlite", type=Path)
    parser.add_argument("--source-sqlite", type=Path, help="SQLite source file for export or verification")
    parser.add_argument("--backup-sqlite", type=Path, help="Create a consistent SQLite backup and hash manifest without overwriting files")
    parser.add_argument("--import-postgres", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--target-url-env",
        default="JAYCODE_MIGRATION_TARGET_URL",
        help="Environment variable holding an isolated jaycode_test_* PostgreSQL URL.",
    )
    parser.add_argument("--report", type=Path, help="New, non-overwriting report file for import or verification.")
    args = parser.parse_args()
    if args.backup_sqlite:
        print(json.dumps(backup_sqlite(args.backup_sqlite), ensure_ascii=False))
        return 0
    if args.export_sqlite:
        result = export_sqlite(args.export_sqlite, args.source_sqlite)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.check and args.source_sqlite:
        result = check_rehearsal(args.source_sqlite, args.target_url_env)
    elif args.import_postgres:
        if not args.source_sqlite:
            raise SystemExit("--import-postgres requires --source-sqlite.")
        result = import_postgres(args.source_sqlite, args.target_url_env)
    elif args.verify:
        if not args.source_sqlite:
            raise SystemExit("--verify requires --source-sqlite.")
        result = verify_postgres(args.source_sqlite, args.target_url_env)
    else:
        print(json.dumps(check(), ensure_ascii=False))
        return 0
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as report_file:
            json.dump(result, report_file, ensure_ascii=False, indent=2)
            report_file.write("\n")
        result = {"report": str(report_path), "format": result["format"], "tables": len(result["tables"])}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
