"""Guarded PostgreSQL database provisioning for the one-time P1 cutover.

This module deliberately does not read ``DATABASE_URL``.  Rehearsal targets
and production cutover targets use different environment variables so a test
command cannot accidentally import into the live application database.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.parse import unquote, urlsplit

from app.persistence.migrate import CUTOVER_DATABASE_NAME, CUTOVER_TARGET_ENV

CUTOVER_ADMIN_ENV = "JAYCODE_CUTOVER_ADMIN_URL"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class CutoverConfigurationError(RuntimeError):
    """The explicit cutover connection pair is not safe to use."""


def _target_identity(url: str, *, expected_database: str, environment_name: str) -> tuple[str, int, str]:
    if not url:
        raise CutoverConfigurationError(f"Set {environment_name}; application DATABASE_URL is never used for cutover.")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    database = unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise CutoverConfigurationError(f"{environment_name} must be a PostgreSQL URL.")
    if host not in _LOOPBACK_HOSTS:
        raise CutoverConfigurationError(f"{environment_name} must target loopback PostgreSQL.")
    if database != expected_database:
        raise CutoverConfigurationError(f"{environment_name} must target database {expected_database}.")
    return ("127.0.0.1" if host == "localhost" else host, parsed.port or 5432, database)


def cutover_urls_from_environment() -> tuple[str, str]:
    return os.getenv(CUTOVER_ADMIN_ENV, "").strip(), os.getenv(CUTOVER_TARGET_ENV, "").strip()


def validate_cutover_urls(admin_url: str, target_url: str) -> dict[str, Any]:
    """Validate the credential-free identity of the explicit maintenance pair."""
    admin = _target_identity(admin_url, expected_database="postgres", environment_name=CUTOVER_ADMIN_ENV)
    target = _target_identity(target_url, expected_database=CUTOVER_DATABASE_NAME, environment_name=CUTOVER_TARGET_ENV)
    if admin[:2] != target[:2]:
        raise CutoverConfigurationError("Cutover admin and target URLs must use the same loopback host and port.")
    return {"host": target[0], "port": target[1], "database": target[2]}


def _connect_admin(admin_url: str) -> Any:
    try:
        from psycopg import connect
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - dependency configuration guard
        raise CutoverConfigurationError("psycopg is required for PostgreSQL cutover.") from exc
    return connect(admin_url, autocommit=True, row_factory=dict_row)


def preflight_cutover(admin_url: str, target_url: str) -> dict[str, Any]:
    """Confirm maintenance access and that the target database is absent."""
    summary = validate_cutover_urls(admin_url, target_url)
    with _connect_admin(admin_url) as connection:
        connection.execute("SELECT 1").fetchone()
        existing = connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (CUTOVER_DATABASE_NAME,)).fetchone()
    if existing:
        raise CutoverConfigurationError(f"Target database {CUTOVER_DATABASE_NAME} already exists; refusing to reuse it.")
    return {**summary, "target_exists": False, "status": "preflight_ok"}


def create_cutover_database(admin_url: str, target_url: str) -> dict[str, Any]:
    """Create the fresh target after a successful maintenance-window preflight."""
    summary = preflight_cutover(admin_url, target_url)
    from psycopg import sql

    with _connect_admin(admin_url) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(CUTOVER_DATABASE_NAME)))
    return {**summary, "created": True, "status": "target_created"}


def drop_newly_created_cutover_database(admin_url: str, target_url: str, confirmation: str) -> dict[str, Any]:
    """Rollback helper; only an exact, explicit confirmation can drop the target."""
    if confirmation != f"DROP_{CUTOVER_DATABASE_NAME.upper()}_CREATED_THIS_RUN":
        raise CutoverConfigurationError("Refusing to drop cutover target without the exact created-this-run confirmation.")
    summary = validate_cutover_urls(admin_url, target_url)
    from psycopg import sql

    with _connect_admin(admin_url) as connection:
        connection.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid <> pg_backend_pid()", (CUTOVER_DATABASE_NAME,))
        connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(CUTOVER_DATABASE_NAME)))
    return {**summary, "dropped": True, "status": "target_dropped"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded Jaycode P1 cutover database operations")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--create-target", action="store_true")
    group.add_argument("--drop-created-target", action="store_true")
    parser.add_argument("--confirm-drop", default="")
    args = parser.parse_args()
    admin_url, target_url = cutover_urls_from_environment()
    if args.preflight:
        result = preflight_cutover(admin_url, target_url)
    elif args.create_target:
        result = create_cutover_database(admin_url, target_url)
    else:
        result = drop_newly_created_cutover_database(admin_url, target_url, args.confirm_drop)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
