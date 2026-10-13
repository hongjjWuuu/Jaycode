from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.project_paths import ProjectPathError, project_collection, resolve_project_path
from app.persistence.rag_store import SQLiteRagStore
from app.schemas.studio import TaskRunRequest
from app.services.legacy_handlers import run_task
from app.services.task_preflight import preflight_task


def _configure_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(settings, "jaycode_workspace_root", str(root))
    monkeypatch.setattr(settings, "jaycode_allowed_project_roots", str(root))


def test_relative_project_path_uses_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "README.md").write_text("demo", encoding="utf-8")
    _configure_roots(monkeypatch, tmp_path)

    resolved = resolve_project_path("demo")

    assert resolved.resolved_path == str(project.resolve())
    assert resolved.project_name == "demo"
    assert resolved.project_id == resolve_project_path(str(project)).project_id
    assert project_collection(resolved.project_id) == f"project::{resolved.project_id}"


def test_project_path_outside_allowed_root_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    _configure_roots(monkeypatch, allowed)

    with pytest.raises(ProjectPathError) as error:
        resolve_project_path(str(outside))

    assert error.value.error_code == "PROJECT_PATH_OUTSIDE_ALLOWED_ROOTS"


def test_project_workflow_requires_path_before_queueing() -> None:
    nodes = [{"id": "analyze", "type": "agent", "config": {"agent_type": "project_analyzer"}}]

    with pytest.raises(ProjectPathError) as error:
        preflight_task(nodes, None)

    assert error.value.error_code == "PROJECT_PATH_REQUIRED"


def test_task_endpoint_preflight_does_not_create_queued_task(monkeypatch: pytest.MonkeyPatch) -> None:
    created = False

    def fail_if_created(**_kwargs: object) -> None:
        nonlocal created
        created = True

    monkeypatch.setattr("app.services.legacy_handlers.harness_runtime.create_context", fail_if_created)
    request = TaskRunRequest(
        goal="analyze",
        project_path=None,
        nodes=[{"id": "analyze", "type": "agent", "config": {"agent_type": "project_analyzer"}}],
    )

    with pytest.raises(HTTPException) as error:
        run_task(request)

    assert error.value.status_code == 422
    assert error.value.detail["error_code"] == "PROJECT_PATH_REQUIRED"
    assert created is False


def test_pure_planner_reporter_workflow_can_run_without_project() -> None:
    result = preflight_task(
        [{"id": "plan", "type": "planner", "config": {}}, {"id": "report", "type": "reporter", "config": {}}],
        None,
    )

    assert result.requires_project is False
    assert result.project is None


def test_legacy_rag_workflow_requires_explicit_scope() -> None:
    nodes = [{"id": "knowledge", "type": "rag", "config": {"collection": "project-memory"}}]

    with pytest.raises(ProjectPathError) as error:
        preflight_task(nodes, None)

    assert error.value.error_code == "KNOWLEDGE_SCOPE_REQUIRED"


def test_explicit_legacy_shared_rag_can_run_without_project() -> None:
    nodes = [{"id": "knowledge", "type": "rag", "config": {"knowledge_scope": "legacy_shared", "collection": "project-memory"}}]

    result = preflight_task(nodes, None)

    assert result.requires_project is False


def test_project_rag_collections_and_metadata_are_isolated(tmp_path: Path) -> None:
    store = SQLiteRagStore(tmp_path / "rag.db")
    for project_id, content in (("alpha", "alpha architecture module details" * 4), ("beta", "beta service boundary details" * 4)):
        collection = project_collection(project_id)
        path = f"{project_id}.md"
        store.ingest(
            collection,
            [{"path": path, "size": len(content), "metadata": {"project_id": project_id}}],
            [{"path": path, "chunk_id": f"{path}#1", "content": content, "metadata": {"project_id": project_id}}],
        )

    alpha_docs = store.list_documents(project_collection("alpha"))
    beta_docs = store.list_documents(project_collection("beta"))
    assert alpha_docs[0]["metadata"]["project_id"] == "alpha"
    assert beta_docs[0]["metadata"]["project_id"] == "beta"
    alpha_hits = store.query(project_collection("alpha"), "beta service", 5)
    assert all(item["path"] == "alpha.md" for item in alpha_hits)
