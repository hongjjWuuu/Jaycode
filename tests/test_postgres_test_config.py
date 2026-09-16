from __future__ import annotations

import pytest
from postgres_test_config import isolated_postgres_url


def test_postgres_test_url_requires_explicit_isolated_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAYCODE_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/jaycode")
    assert isolated_postgres_url() == ""


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/jaycode_test_contract",
        "postgres://tester:password@127.0.0.1:5432/jaycode_test_contract",
        "postgresql://tester@[::1]:5432/jaycode_test_contract",
    ],
)
def test_postgres_test_url_accepts_loopback_isolated_database(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setenv("JAYCODE_TEST_DATABASE_URL", url)
    assert isolated_postgres_url() == url


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/jaycode_test_contract",
        "postgresql://db.example.com/jaycode_test_contract",
        "postgresql://localhost/jaycode",
    ],
)
def test_postgres_test_url_rejects_unsafe_targets_before_connection(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setenv("JAYCODE_TEST_DATABASE_URL", url)
    with pytest.raises(RuntimeError):
        isolated_postgres_url()
