from __future__ import annotations

import pytest

from scripts.run_postgres_contracts import _admin_target, _child_url, _contains_skips


def test_postgres_runner_requires_dedicated_admin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAYCODE_TEST_ADMIN_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/jaycode")
    with pytest.raises(RuntimeError, match="JAYCODE_TEST_ADMIN_URL"):
        _admin_target()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://tester:secret@db.example.com:5432/postgres",
        "postgresql://tester:secret@localhost:5432/jaycode",
        "https://localhost/postgres",
    ],
)
def test_postgres_runner_rejects_non_loopback_or_non_maintenance_targets(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setenv("JAYCODE_TEST_ADMIN_URL", url)
    with pytest.raises(RuntimeError):
        _admin_target()


def test_postgres_runner_builds_child_url_for_random_test_database() -> None:
    admin_url = "postgresql://tester:secret@[::1]:5432/postgres?sslmode=disable"
    assert _child_url(admin_url, "jaycode_test_abc123") == (
        "postgresql://tester:secret@[::1]:5432/jaycode_test_abc123?sslmode=disable"
    )


def test_postgres_runner_detects_skipped_contract_tests() -> None:
    assert _contains_skips("12 passed, 1 skipped in 2.4s")
    assert not _contains_skips("13 passed in 2.4s")
