"""Create, run against, and drop one owned local PostgreSQL test database."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
REPO_ROOT = Path(__file__).resolve().parents[1]
PG_URL_PATTERN = re.compile(r"(?i)\bpostgres(?:ql)?://[^\s'\"]+")
SECRET_PATTERN = re.compile(r"(?i)\b(password|pwd|token|secret|api[_-]?key)=([^\s&]+)")


def _redact(text: str, *urls: str) -> str:
    for url in urls:
        if url:
            text = text.replace(url, "[REDACTED_POSTGRES_URL]")
    text = PG_URL_PATTERN.sub("[REDACTED_POSTGRES_URL]", text)
    return SECRET_PATTERN.sub(r"\1=[REDACTED]", text)


def _admin_target() -> tuple[str, str]:
    admin_url = os.getenv("JAYCODE_TEST_ADMIN_URL", "").strip()
    if not admin_url:
        raise RuntimeError("Set JAYCODE_TEST_ADMIN_URL to a loopback PostgreSQL maintenance database URL.")
    parsed = urlsplit(admin_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("JAYCODE_TEST_ADMIN_URL must use postgres or postgresql scheme.")
    if (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
        raise RuntimeError("PostgreSQL test database creation is restricted to loopback hosts.")
    if parsed.path.lstrip("/") != "postgres":
        raise RuntimeError("JAYCODE_TEST_ADMIN_URL must connect to the 'postgres' maintenance database.")
    return admin_url, parsed.hostname or ""


def _child_url(admin_url: str, database: str) -> str:
    parsed = urlsplit(admin_url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{quote(database)}", parsed.query, parsed.fragment))


def _run() -> int:
    admin_url, _ = _admin_target()
    import psycopg
    from psycopg import sql

    database = f"jaycode_test_{uuid4().hex}"
    test_url = _child_url(admin_url, database)
    created = False
    exit_code = 1
    try:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone()
            if exists:
                raise RuntimeError("Random test database name already exists; refusing to use it.")
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
        created = True
        environment = os.environ.copy()
        environment["JAYCODE_TEST_DATABASE_URL"] = test_url
        environment["JAYCODE_MIGRATION_TARGET_URL"] = test_url
        environment["DATABASE_URL"] = test_url
        environment["PGVECTOR_DATABASE_URL"] = test_url
        environment["JAYCODE_PERSISTENCE_STORE"] = "postgres"
        environment["JAYCODE_RAG_STORE"] = "pgvector"
        environment["JAYCODE_TEST_MODE"] = "1"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_postgres_migration_rehearsal.py",
            "tests/test_postgres_store.py",
            "tests/test_postgres_memory_store.py",
            "tests/test_postgres_rag_store.py",
            "tests/test_postgres_test_config.py",
            "tests/test_postgres_migrations.py",
            "tests/test_cross_backend_contracts.py",
            "tests/test_postgres_e2e.py",
        ]
        result = subprocess.run(command, cwd=REPO_ROOT, env=environment, capture_output=True, text=True, check=False)
        exit_code = result.returncode
        output = _redact(result.stdout + result.stderr, admin_url, test_url)
        print(f"Temporary PostgreSQL test database: {database}")
        print(output, end="" if output.endswith("\n") or not output else "\n")
    except (psycopg.Error, OSError) as exc:
        print(f"PostgreSQL isolated test operation failed ({type(exc).__name__}).", file=sys.stderr)
        exit_code = 2
    finally:
        if created:
            try:
                with psycopg.connect(admin_url, autocommit=True) as connection:
                    connection.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
                    )
                print(f"Dropped this run's PostgreSQL test database: {database}")
            except psycopg.Error as exc:
                print(f"ERROR: failed to drop temporary database {database} ({type(exc).__name__}).", file=sys.stderr)
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(_run())
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        print(f"PostgreSQL isolated test setup failed: {type(exc).__name__}.", file=sys.stderr)
        raise SystemExit(2) from None
