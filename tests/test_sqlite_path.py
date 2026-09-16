from __future__ import annotations

from pathlib import Path

from app.persistence.sqlite_path import DEFAULT_SQLITE_PATH, resolve_sqlite_path


def test_test_sqlite_override_is_used_only_without_explicit_path(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "isolated.db"
    explicit = tmp_path / "explicit.db"
    monkeypatch.setenv("JAYCODE_TEST_SQLITE_PATH", str(override))
    monkeypatch.setenv("JAYCODE_TEST_MODE", "1")
    assert resolve_sqlite_path() == override
    assert resolve_sqlite_path(explicit) == explicit


def test_default_sqlite_path_is_unchanged_without_test_override(monkeypatch) -> None:
    monkeypatch.delenv("JAYCODE_TEST_SQLITE_PATH", raising=False)
    monkeypatch.delenv("JAYCODE_TEST_MODE", raising=False)
    assert resolve_sqlite_path() == DEFAULT_SQLITE_PATH


def test_test_path_override_is_ignored_without_test_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JAYCODE_TEST_SQLITE_PATH", str(tmp_path / "must-not-use.db"))
    monkeypatch.delenv("JAYCODE_TEST_MODE", raising=False)
    assert resolve_sqlite_path() == DEFAULT_SQLITE_PATH
