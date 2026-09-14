import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def local_test_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy smoke tests in explicit local-development mode."""
    monkeypatch.setattr(settings, "jaycode_auth_enabled", False)
