from fastapi.testclient import TestClient

from app.agents.rag_tools import _chunk_text
from app.core.config import settings
from app.core.llm_monitor import LLMMonitor
from app.core.security import validate_security_configuration
from app.graphs.workflow_compiler import validate_workflow_definition
from app.harness.events import utc_now_iso
from app.harness.load_test import run_worker_load_test
from app.main import app
from app.persistence.memory_store import SQLiteMemoryStore
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


def test_task_api_enqueues_work_for_worker() -> None:
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
    assert task["status"] == "queued"
    persisted = client.get(f"/api/v1/tasks/{task['task_id']}").json()["task"]
    assert persisted["status"] == "queued"


def test_legacy_collaboration_api_enqueues_work_for_worker() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/agents/collaborate",
        json={"goal": "background collaboration", "project_path": "."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["task_id"]
    assert payload["result"] == {}


def test_task_bundle_rolls_back_as_a_unit(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "bundle.db")
    store.create_task("bundle-task", "goal", ".", "running")
    try:
        store.save_task_bundle(
            "bundle-task", "completed", "report", [("result", "result", object())],
            [{"event_id": "bundle-event", "task_id": "bundle-task", "type": "task", "status": "completed"}],
        )
    except TypeError:
        pass
    else:
        raise AssertionError("Non-serializable artifact must abort the transaction")
    assert store.get_task("bundle-task")["status"] == "running"
    assert store.get_artifacts("bundle-task") == []
    assert store.get_events("bundle-task") == []


def test_review_resume_is_enqueued_atomically(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "resume.db")
    store.create_task("resume-task", "goal", ".", "waiting_review", input_state={"goal": "goal"})
    store.queue_task_resume("resume-task", {"paused_node_id": "review"}, "approved", "ok")
    task = store.get_task("resume-task")
    assert task["status"] == "queued"
    assert task["resume_count"] == 1
    assert store.get_task_input("resume-task")["_jaycode_runner"] == "resume"
    assert store.get_events("resume-task")[-1]["status"] == "queued"


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


def test_sqlite_task_lease_claim_and_heartbeat(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "lease.db")
    store.create_task("lease-task", "lease", ".", "queued", input_state={"goal": "lease"})
    claimed = store.claim_task("lease-task", "worker-a", lease_seconds=30)
    assert claimed and claimed["worker_id"] == "worker-a"
    assert claimed["attempt"] == 1
    assert store.claim_task("lease-task", "worker-b") is None
    assert store.heartbeat_task("lease-task", "worker-a") is True
    assert store.heartbeat_task("lease-task", "worker-b") is False
    assert store.get_task_input("lease-task") == {"goal": "lease"}


def test_expired_lease_recovery_and_cancel_are_audited(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "worker-events.db")
    store.create_task("recover-task", "recover", ".", "queued")
    assert store.claim_task("recover-task", "dead-worker", lease_seconds=30)
    with store._connect() as conn:
        conn.execute("UPDATE agent_task SET lease_until = '2000-01-01, 00:00:00' WHERE task_id = 'recover-task'")
    assert store.recover_expired_task_ids() == ["recover-task"]
    assert store.get_task("recover-task")["status"] == "queued"
    assert store.get_events("recover-task")[-1]["type"] == "worker_recovered"
    assert store.cancel_task("recover-task") is True
    assert store.get_task("recover-task")["status"] == "cancelled"
    assert store.get_events("recover-task")[-1]["type"] == "task_cancelled"


def test_workflow_declared_output_contract_is_validated() -> None:
    result = validate_workflow_definition(
        [{"id": "report", "type": "reporter", "config": {"output_schema": {"final_report": "string", "count": "integer"}}}],
        [],
    )
    assert result["valid"] is True


def test_workflow_cross_node_mapping_type_is_checked() -> None:
    nodes = [
        {"id": "plan", "type": "planner"},
        {"id": "agent", "type": "agent", "config": {"input_mappings": {"input_text": "plan.plan"}}},
        {"id": "report", "type": "reporter"},
    ]
    edges = [{"source": "plan", "target": "agent"}, {"source": "agent", "target": "report"}]
    result = validate_workflow_definition(nodes, edges)
    assert result["valid"] is False
    assert any("maps `plan.plan` (object) to `input_text` (string)" in error for error in result["errors"])


def test_worker_load_test_claims_each_task_once(tmp_path) -> None:
    result = run_worker_load_test(tmp_path / "worker-load.db", task_count=100, worker_count=2)
    assert result["claimed_count"] == 100
    assert result["unique_claimed_count"] == 100
    assert result["completed_count"] == 100
    assert result["throughput_tasks_per_second"] > 0


def test_llm_monitor_emits_dimensioned_metrics_and_threshold_alerts() -> None:
    from app.core.observability import metrics

    monitor = LLMMonitor()
    now = utc_now_iso()
    traces = [
        {
            "model": "model-a",
            "agent": "reviewer",
            "prompt_version": "v2",
            "fallback_used": index < 6,
            "error_message": "schema invalid" if index < 2 else None,
            "latency_ms": 40000 if index == 19 else 100,
            "token_usage": {"total_tokens": 7},
            "created_at": now,
            "input": "sensitive prompt must not be exported",
        }
        for index in range(20)
    ]
    alerts = monitor.collect(traces)
    assert {alert["name"] for alert in alerts} == {"llm_fallback_rate", "llm_schema_failure_rate", "llm_p95_latency_ms"}
    rendered = metrics.render()
    assert 'model="model-a"' in rendered
    assert "sensitive prompt" not in rendered


def test_postgres_selection_fails_closed_until_all_domains_are_wired(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jaycode_persistence_store", "postgres")
    monkeypatch.setattr(settings, "database_url", "postgresql://unused")
    try:
        validate_security_configuration()
    except RuntimeError as exc:
        assert "refusing mixed" in str(exc)
    else:
        raise AssertionError("PostgreSQL must not silently leave application domains on SQLite")


def test_memory_lifecycle_is_audited(tmp_path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    records = store.extract_candidates("我希望优先关注安全风险", actor_id="actor-1")
    assert records
    memory_id = records[0]["memory_id"]
    assert store.reject(memory_id, actor_id="actor-1")
    events = store.list_lifecycle_events(memory_id)
    assert [event["action"] for event in events] == ["created", "rejected"]
