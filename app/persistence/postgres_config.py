"""PostgreSQL target validation shared by application startup and migration tools."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit


def database_target_key(database_url: str) -> tuple[str, int, str]:
    """Return a credential-free identity for a PostgreSQL database target."""
    parsed = urlsplit(database_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    database = unquote(parsed.path.lstrip("/"))
    if not host or not database:
        raise ValueError("PostgreSQL URL must include a host and database name.")
    if host == "localhost":
        host = "127.0.0.1"
    return host, parsed.port or 5432, database


def validate_matching_postgres_targets(database_url: str, pgvector_database_url: str) -> None:
    """Reject split persistence when RAG and the primary store target differ."""
    if database_url and pgvector_database_url and database_target_key(database_url) != database_target_key(pgvector_database_url):
        raise RuntimeError("DATABASE_URL and PGVECTOR_DATABASE_URL must target the same PostgreSQL database.")
