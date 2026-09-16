import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Set before test modules import the application and construct global stores.
_REQUESTED_SQLITE_PATH = os.getenv("JAYCODE_TEST_SQLITE_PATH")
_REQUESTED_OWNER_TOKEN = os.getenv("JAYCODE_TEST_SQLITE_OWNER_TOKEN")
_REQUESTED_ROOT = Path(_REQUESTED_SQLITE_PATH).resolve().parent if _REQUESTED_SQLITE_PATH else None
_REQUESTED_OWNER_FILE = (
    _REQUESTED_ROOT.with_name(f"{_REQUESTED_ROOT.name}.owner") if _REQUESTED_ROOT else None
)
_REQUESTED_RUNNER_OWNS_ROOT = bool(
    _REQUESTED_ROOT
    and _REQUESTED_OWNER_TOKEN
    and _REQUESTED_ROOT.name.startswith("jaycode-test-sqlite-")
    and _REQUESTED_ROOT.parent == Path(tempfile.gettempdir()).resolve()
    and _REQUESTED_OWNER_FILE
    and _REQUESTED_OWNER_FILE.is_file()
    and _REQUESTED_OWNER_FILE.read_text(encoding="ascii") == _REQUESTED_OWNER_TOKEN
)
_OWNS_SQLITE_ROOT = not _REQUESTED_RUNNER_OWNS_ROOT
if _REQUESTED_RUNNER_OWNS_ROOT:
    _TEST_SQLITE_ROOT = _REQUESTED_ROOT
else:
    _TEST_SQLITE_ROOT = Path(tempfile.mkdtemp(prefix="jaycode-test-sqlite-")).resolve()
    _TEST_SQLITE_OWNER = uuid4().hex
    _TEST_SQLITE_OWNER_FILE = _TEST_SQLITE_ROOT.with_name(f"{_TEST_SQLITE_ROOT.name}.owner")
    _TEST_SQLITE_OWNER_FILE.write_text(_TEST_SQLITE_OWNER, encoding="ascii")
    os.environ["JAYCODE_TEST_SQLITE_PATH"] = str(_TEST_SQLITE_ROOT / "test.db")
    os.environ["JAYCODE_TEST_SQLITE_OWNER_TOKEN"] = _TEST_SQLITE_OWNER
os.environ["JAYCODE_TEST_MODE"] = "1"

from app.core.config import settings


@pytest.fixture(autouse=True)
def local_test_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy smoke tests in explicit local-development mode."""
    monkeypatch.setattr(settings, "jaycode_auth_enabled", False)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove only the exact temporary SQLite directory created by this run."""
    if not _OWNS_SQLITE_ROOT:
        return
    temp_root = Path(tempfile.gettempdir()).resolve()
    candidate = _TEST_SQLITE_ROOT.resolve()
    owner_file = (
        _TEST_SQLITE_OWNER_FILE
        if _OWNS_SQLITE_ROOT
        else _REQUESTED_OWNER_FILE
    )
    owner_token = _TEST_SQLITE_OWNER if _OWNS_SQLITE_ROOT else _REQUESTED_OWNER_TOKEN
    if (
        candidate.parent != temp_root
        or not candidate.name.startswith("jaycode-test-sqlite-")
        or not owner_file.is_file()
        or owner_file.read_text(encoding="ascii") != owner_token
    ):
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_line("WARNING: isolated SQLite temp directory ownership check failed; preserved it.")
        return
    try:
        shutil.rmtree(candidate)
        owner_file.unlink()
    except OSError as exc:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_line(f"WARNING: could not clean isolated SQLite directory; preserved it ({type(exc).__name__}).")
