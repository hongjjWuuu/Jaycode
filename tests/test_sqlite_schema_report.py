from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.sqlite_schema_report import inspect_sqlite_schema


def test_sqlite_schema_inventory_is_read_only_and_excludes_row_content(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 7")
        connection.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY, secret TEXT NOT NULL)")
        connection.execute("CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))")
        connection.execute("INSERT INTO parent VALUES (1, 'DO_NOT_EXPORT_SENTINEL')")

    report = inspect_sqlite_schema(database)
    assert report["user_version"] == 7
    assert report["table_count"] == 2
    assert report["tables"]["parent"]["row_count"] == 1
    assert report["tables"]["child"]["foreign_keys"][0]["referenced_table"] == "parent"
    assert report["content_included"] is False
    assert "DO_NOT_EXPORT_SENTINEL" not in str(report)

    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT secret FROM parent").fetchone()[0] == "DO_NOT_EXPORT_SENTINEL"
