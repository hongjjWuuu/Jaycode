from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from postgres_test_config import isolated_postgres_url

from app.persistence.postgres_store import PostgresTaskStore
from app.persistence.sqlite_store import SQLiteTaskStore


pytestmark = pytest.mark.postgres
DATABASE_URL = isolated_postgres_url()


@pytest.fixture(params=["sqlite", "postgres"])
def task_store(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "sqlite":
        return SQLiteTaskStore(tmp_path / "contract.sqlite3")
    if not DATABASE_URL:
        pytest.skip("set JAYCODE_TEST_DATABASE_URL to an isolated local test database")
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    return store


def test_shared_core_persistence_contract(task_store) -> None:
    """Exercise identical task/workflow/audit/LLM/benchmark semantics on both backends."""
    suffix = uuid4().hex
    task_id = f"cross-task-{suffix}"
    workflow_id = f"cross-workflow-{suffix}"
    run_id = f"cross-run-{suffix}"
    trace_id = f"cross-trace-{suffix}"
    agent = f"cross-agent-{suffix}"

    task_store.create_task(
        task_id,
        "cross backend contract",
        None,
        "queued",
        {"idempotency_key": f"cross-key-{suffix}"},
        {"source": "contract"},
    )
    assert task_store.get_task(task_id)["status"] == "queued"
    assert task_store.get_task_input(task_id) == {"source": "contract"}

    workflow = task_store.save_workflow(workflow_id, "Cross contract", "shared", [{"id": "start"}], [])
    assert workflow["workflow_id"] == workflow_id
    assert task_store.get_workflow(workflow_id)["nodes"] == [{"id": "start"}]

    audit = task_store.save_security_audit(
        {
            "request_id": f"cross-request-{suffix}",
            "actor_id": "contract-actor",
            "role": "admin",
            "action": "cross_contract",
            "resource_type": "test",
            "resource_id": task_id,
            "status": "completed",
            "metadata": {"backend": type(task_store).__name__},
        }
    )
    assert audit["action"] == "cross_contract"

    trace = task_store.save_llm_trace(
        {
            "trace_id": trace_id,
            "agent": agent,
            "prompt_version": "cross.v1",
            "model": "deterministic-test-model",
            "input": {"contract": True},
            "output": "ok",
            "latency_ms": 1,
            "token_usage": {"total_tokens": 1},
        }
    )
    assert trace["trace_id"] == trace_id
    assert task_store.list_llm_traces(agent=agent)[0]["trace_id"] == trace_id

    task_store.upsert_prompt_version(
        {"agent": agent, "prompt_version": "cross.v1", "title": "Cross", "system_suffix": "shared"}
    )
    assert task_store.get_prompt_version(agent, "cross.v1")["system_suffix"] == "shared"

    run = task_store.create_benchmark_run(run_id, "Cross backend", "rag", {"dataset_version": "test"})
    assert run["status"] == "running"
    task_store.append_benchmark_result(
        {"run_id": run_id, "case_id": "contract", "status": "passed", "input": {}, "output": {}}
    )
    assert task_store.finish_benchmark_run(run_id, "completed", {"passed": 1})["status"] == "completed"
    assert task_store.claim_task(task_id, f"cross-worker-{suffix}", lease_seconds=20)
    task_store.save_task_bundle(
        task_id,
        "completed",
        "shared contract completed",
        [],
        [{"event_id": f"cross-event-{suffix}", "task_id": task_id, "type": "task", "status": "completed"}],
    )
