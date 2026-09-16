"""Create a content-free, read-only inventory of a SQLite schema."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def inspect_sqlite_schema(database: Path) -> dict[str, Any]:
    database = database.resolve(strict=True)
    if not database.is_file():
        raise FileNotFoundError("SQLite database path is not a file.")
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables: dict[str, Any] = {}
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            table = str(row[0])
            quoted = table.replace('"', '""')
            columns = connection.execute(f'PRAGMA table_info("{quoted}")').fetchall()
            foreign_keys = connection.execute(f'PRAGMA foreign_key_list("{quoted}")').fetchall()
            count = int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
            tables[table] = {
                "row_count": count,
                "columns": [
                    {
                        "name": str(column[1]),
                        "type": str(column[2] or ""),
                        "not_null": bool(column[3]),
                        "primary_key_position": int(column[5]),
                    }
                    for column in columns
                ],
                "foreign_keys": [
                    {
                        "referenced_table": str(foreign_key[2]),
                        "column": str(foreign_key[3]),
                        "referenced_column": str(foreign_key[4]),
                        "on_update": str(foreign_key[5]),
                        "on_delete": str(foreign_key[6]),
                    }
                    for foreign_key in foreign_keys
                ],
            }

        version_metadata: list[dict[str, Any]] = []
        for table in ("schema_version", "jaycode_schema_version", "schema_migrations", "alembic_version"):
            if table not in tables:
                continue
            candidates = {"version", "schema_version", "current_version"}
            version_columns = [column["name"] for column in tables[table]["columns"] if column["name"].lower() in candidates]
            for column in version_columns:
                quoted_table = table.replace('"', '""')
                quoted_column = column.replace('"', '""')
                values = connection.execute(
                    f'SELECT DISTINCT "{quoted_column}" FROM "{quoted_table}" LIMIT 20'
                ).fetchall()
                version_metadata.append({"table": table, "column": column, "values": [item[0] for item in values]})

        return {
            "format": "jaycode-sqlite-schema-inventory-v1",
            "source_name": database.name,
            "user_version": user_version,
            "schema_version_metadata": version_metadata,
            "table_count": len(tables),
            "tables": tables,
            "content_included": False,
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/dev_agent_studio.db"))
    parser.add_argument("--output", type=Path, required=True, help="New report file; existing files are never overwritten.")
    args = parser.parse_args()
    report = inspect_sqlite_schema(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"SQLite schema inventory written: {args.output} ({report['table_count']} tables; no row contents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
