"""Versioned, checksum-protected PostgreSQL schema migration execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PostgresMigration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        payload = "\n-- statement --\n".join(statement.strip() for statement in self.statements)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_postgres_migrations(connection: Any, migrations: tuple[PostgresMigration, ...]) -> None:
    """Apply ordered migrations atomically and reject history/checksum drift."""
    connection.execute(
        """CREATE TABLE IF NOT EXISTS jaycode_schema_migration (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    applied = {
        int(row["version"]): row
        for row in connection.execute("SELECT version, name, checksum FROM jaycode_schema_migration").fetchall()
    }
    expected_version = migrations[0].version if applied else 1
    for migration in migrations:
        if migration.version != expected_version:
            raise RuntimeError(f"PostgreSQL migration sequence must be contiguous; expected {expected_version}.")
        expected_version += 1
        previous = applied.get(migration.version)
        if previous:
            if previous["name"] != migration.name or previous["checksum"] != migration.checksum:
                raise RuntimeError(f"PostgreSQL migration checksum mismatch at version {migration.version}.")
            continue
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO jaycode_schema_migration(version, name, checksum) VALUES (%s, %s, %s)",
            (migration.version, migration.name, migration.checksum),
        )


def assert_pgvector_available(connection: Any) -> None:
    """Fail before migration if this database cannot provide the RAG extension."""
    available = connection.execute(
        "SELECT 1 FROM pg_available_extensions WHERE name='vector'"
    ).fetchone()
    if not available:
        raise RuntimeError("PostgreSQL pgvector extension is unavailable for this database.")
