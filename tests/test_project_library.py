from pathlib import Path

import pytest

from app.core.config import settings
from app.core.project_paths import ProjectPathError, browse_project_directories, project_browser_roots, resolve_project_path
from app.persistence.sqlite_store import SQLiteTaskStore


def test_directory_browser_is_scoped_to_configured_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    project = root / "team" / "demo"
    project.mkdir(parents=True)
    monkeypatch.setattr(settings, "jaycode_workspace_root", str(root))
    monkeypatch.setattr(settings, "jaycode_allowed_project_roots", str(root))

    browser_root = project_browser_roots()[0]
    first_level = browse_project_directories(browser_root["root_id"])
    assert first_level["directories"] == [{"name": "team", "relative_path": "team"}]
    assert browse_project_directories(browser_root["root_id"], "team")["directories"][0]["name"] == "demo"
    with pytest.raises(ProjectPathError) as error:
        browse_project_directories(browser_root["root_id"], "../outside")
    assert error.value.error_code == "PROJECT_PATH_OUTSIDE_ALLOWED_ROOTS"


def test_personal_project_library_isolated_and_can_be_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    monkeypatch.setattr(settings, "jaycode_workspace_root", str(tmp_path))
    monkeypatch.setattr(settings, "jaycode_allowed_project_roots", str(tmp_path))
    resolved = resolve_project_path(str(project))
    store = SQLiteTaskStore(tmp_path / "jaycode.db")

    saved = store.save_registered_project("alice", "Demo", resolved.resolved_path, resolved.project_id)
    assert [item["name"] for item in store.list_registered_projects("alice")] == ["Demo"]
    assert store.list_registered_projects("bob") == []
    assert store.update_registered_project(saved["registered_project_id"], "admin", True, enabled=False)
    assert store.list_registered_projects("alice") == []
    assert store.list_registered_projects("alice", include_disabled=True)[0]["enabled"] is False
