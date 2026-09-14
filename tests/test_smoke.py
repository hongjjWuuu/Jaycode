from fastapi.testclient import TestClient

from app.agents.rag_tools import _chunk_text
from app.graphs.workflow_compiler import validate_workflow_definition
from app.main import app
from app.persistence.rag_store import evaluate_gold_set
from app.persistence.sqlite_store import SQLiteTaskStore


def test_web_app_can_be_created() -> None:
    assert app.title == "Jaycode"


def test_control_plane_health_and_catalogs() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/skills").status_code == 200
    assert client.get("/api/v1/marketplace/catalog").status_code == 200
    assert client.get("/api/v1/rag/status").status_code == 200
    assert client.get("/api/v1/benchmarks").status_code == 200


def test_workflow_validation() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/workflows/validate",
        json={
            "nodes": [
                {"id": "plan", "type": "planner"},
                {"id": "report", "type": "reporter"},
            ],
            "edges": [{"source": "plan", "target": "report"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_task_review_resume() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/tasks/run",
        json={
            "goal": "smoke review resume",
            "project_path": ".",
            "require_human_review": True,
            "nodes": [
                {"id": "plan", "type": "planner"},
                {"id": "review", "type": "human_review"},
                {"id": "report", "type": "reporter"},
            ],
            "edges": [
                {"source": "plan", "target": "review"},
                {"source": "review", "target": "report"},
            ],
        },
    )
    assert response.status_code == 200
    task = response.json()
    assert task["status"] == "waiting_review"

    approved = client.post(
        f"/api/v1/tasks/{task['task_id']}/approve",
        json={"comment": "test approval"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"


def test_workflow_cycles_and_disconnected_nodes_are_blocked() -> None:
    result = validate_workflow_definition(
        [{"id": "a", "type": "planner"}, {"id": "b", "type": "reporter"}, {"id": "orphan", "type": "reporter"}],
        [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    )
    assert result["valid"] is False
    assert any("cycle" in item.lower() for item in result["errors"])
    assert any("disconnected" in item.lower() for item in result["errors"])


def test_sqlite_task_idempotency_events_and_pragmas(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "p1.db")
    assert store._connect().execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    context = {"idempotency_key": "same-request", "actor_id": "actor", "role": "user"}
    assert store.create_task("task-one", "goal", ".", "created", context) is None
    existing = store.create_task("task-two", "goal", ".", "created", context)
    assert existing and existing["task_id"] == "task-one"
    event = {"event_id": "event-one", "task_id": "task-one", "type": "task", "content": "once"}
    store.append_event(event)
    store.append_event(event)
    assert len(store.get_events("task-one")) == 1


def test_rag_chunks_include_source_metadata() -> None:
    chunks = _chunk_text("app/example.py", "line one\n" * 30)
    assert chunks
    assert chunks[0]["metadata"]["language"] == "py"
    assert chunks[0]["metadata"]["module_name"] == "example"


def test_rag_gold_set_reports_recall_and_mrr() -> None:
    class FakeRagStore:
        def list_gold_cases(self, collection=None, include_disabled=False):
            return [{"case_id": "gold-1", "collection": "docs", "question": "workflow", "expected_chunk_ids": ["docs#1"], "expected_paths": [], "expected_keywords": ["workflow"]}]

        def query(self, collection, question, limit=5, actor_id="local-user"):
            return [{"chunk_id": "docs#1", "path": "docs/workflow.md", "content": "Workflow validation"}]

    result = evaluate_gold_set(FakeRagStore())
    assert result["recall_at_k"] == 1.0
    assert result["mrr"] == 1.0
    assert result["keyword_coverage"] == 1.0
