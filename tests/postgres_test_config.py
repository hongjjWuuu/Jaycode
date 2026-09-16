"""Safety checks for opt-in PostgreSQL integration tests.

Integration tests are destructive within their target database (they create
schemas and tables), so they must never consume the application's DATABASE_URL.
"""

from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit


def isolated_postgres_url() -> str:
    """Return an explicitly isolated local test URL or an empty string.

    Requiring a dedicated variable and database-name prefix prevents an
    accidental test run against the configured application database.
    """
    database_url = os.getenv("JAYCODE_TEST_DATABASE_URL", "").strip()
    if not database_url:
        return ""

    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("PostgreSQL contract test URL must use postgres or postgresql scheme.")
    host = (parsed.hostname or "").lower()
    database = unquote(parsed.path.lstrip("/"))
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("PostgreSQL contract tests only allow a loopback test database.")
    if not database.startswith("jaycode_test_"):
        raise RuntimeError("Test database name must start with 'jaycode_test_'.")
    return database_url
