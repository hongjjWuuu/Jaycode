"""Resolve SQLite paths while allowing tests to isolate the default database."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SQLITE_PATH = Path("data/dev_agent_studio.db")


def resolve_sqlite_path(db_path: str | Path | None = None) -> Path:
    """Use explicit paths first, then the test-only override, then app default."""
    if db_path is not None:
        return Path(db_path)
    test_path = os.getenv("JAYCODE_TEST_SQLITE_PATH")
    if os.getenv("JAYCODE_TEST_MODE") == "1" and test_path:
        return Path(test_path)
    return DEFAULT_SQLITE_PATH
