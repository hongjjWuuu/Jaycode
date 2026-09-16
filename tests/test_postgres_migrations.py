from __future__ import annotations

import pytest

from app.persistence.postgres_migrations import PostgresMigration, apply_postgres_migrations


class _Cursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class _Connection:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(self, statement: str, params: tuple[object, ...] | None = None) -> _Cursor:
        self.executed.append((statement, params))
        if statement.startswith("SELECT version"):
            return _Cursor(self.rows)
        if statement.startswith("INSERT INTO jaycode_schema_migration"):
            assert params is not None
            self.rows.append({"version": params[0], "name": params[1], "checksum": params[2]})
        return _Cursor([])


def test_versioned_migrations_are_idempotent_and_checksum_protected() -> None:
    connection = _Connection()
    migration = PostgresMigration(1, "core", ("CREATE TABLE demo(id integer)",))
    apply_postgres_migrations(connection, (migration,))
    first_count = len(connection.executed)
    apply_postgres_migrations(connection, (migration,))
    assert len(connection.executed) > first_count
    assert sum("CREATE TABLE demo" in statement for statement, _ in connection.executed) == 1
    drift = PostgresMigration(1, "core", ("CREATE TABLE demo(id text)",))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        apply_postgres_migrations(connection, (drift,))


def test_migrations_reject_non_contiguous_versions() -> None:
    with pytest.raises(RuntimeError, match="contiguous"):
        apply_postgres_migrations(_Connection(), (PostgresMigration(2, "invalid", ("SELECT 1",)),))
