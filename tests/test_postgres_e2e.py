from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from postgres_test_config import isolated_postgres_url

DATABASE_URL = isolated_postgres_url()
pytestmark = pytest.mark.postgres


def _complete_claimed_tasks(database_url: str, worker_id: str) -> list[str]:
    from app.persistence.postgres_store import PostgresTaskStore

    store = PostgresTaskStore(database_url)
    completed: list[str] = []
    while record := store.claim_next_task(worker_id, lease_seconds=20):
        task_id = str(record["task_id"])
        store.save_task_bundle(
            task_id,
            "completed",
            "synthetic worker result",
            [("synthetic", "result", {"worker_id": worker_id})],
            [{"event_id": f"e2e-{task_id}", "task_id": task_id, "type": "task", "status": "completed"}],
        )
        completed.append(task_id)
    return completed


def _complete_claimed_tasks_in_process(arguments: tuple[str, str]) -> list[str]:
    return _complete_claimed_tasks(*arguments)


@pytest.fixture
def postgres_runtime(monkeypatch: pytest.MonkeyPatch):
    if not DATABASE_URL:
        pytest.skip("set JAYCODE_TEST_DATABASE_URL to an isolated local test database")
    from app.core.config import settings
    from app.persistence.factory import get_persistence_stores

    monkeypatch.setattr(settings, "jaycode_persistence_store", "postgres")
    monkeypatch.setattr(settings, "database_url", DATABASE_URL)
    monkeypatch.setattr(settings, "pgvector_database_url", DATABASE_URL)
    monkeypatch.setattr(settings, "jaycode_worker_supervisor_enabled", False)
    monkeypatch.setattr(settings, "jaycode_auth_enabled", False)
    monkeypatch.setattr(settings, "app_env", "dev")
    get_persistence_stores.cache_clear()
    try:
        yield get_persistence_stores()
    finally:
        get_persistence_stores.cache_clear()


def test_postgres_factory_api_queue_and_readiness(postgres_runtime) -> None:
    from app.main import app

    assert postgres_runtime.backend == "postgres"
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        response = client.post(
            "/api/v1/tasks/run",
            json={"goal": "postgres e2e queue", "project_path": ".", "idempotency_key": f"e2e-{uuid4().hex}"},
        )
        assert response.status_code == 200
        task_id = response.json()["task_id"]
        assert response.json()["status"] == "queued"
        persisted = client.get(f"/api/v1/tasks/{task_id}").json()["task"]
        assert persisted["status"] == "queued"
        cancelled = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert cancelled.status_code == 200
        assert client.get(f"/api/v1/tasks/{task_id}").json()["task"]["status"] == "cancelled"

        review_task_id = f"e2e-review-{uuid4().hex}"
        postgres_runtime.task.create_task(review_task_id, "review", None, "waiting_review")
        approved = client.post(f"/api/v1/tasks/{review_task_id}/approve", json={"comment": "approved in e2e"})
        assert approved.status_code == 200
        review_task = client.get(f"/api/v1/tasks/{review_task_id}").json()
        assert review_task["task"]["status"] == "completed"
        assert review_task["artifacts"] == []


def test_two_independent_workers_do_not_duplicate_claims(postgres_runtime) -> None:
    store = postgres_runtime.task
    task_ids = [f"e2e-worker-{uuid4().hex}" for _ in range(10)]
    for task_id in task_ids:
        store.create_task(task_id, "synthetic", None, "queued", input_state={"synthetic": True})
    with ProcessPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                _complete_claimed_tasks_in_process,
                [(DATABASE_URL, "worker-a"), (DATABASE_URL, "worker-b")],
            )
        )
    claimed = [task_id for result in results for task_id in result]
    claimed_for_this_test = [task_id for task_id in claimed if task_id in task_ids]
    # Other contract tests can legitimately leave their own queued synthetic
    # task in this shared, disposable database. The Worker contract is that
    # every task created by this test is claimed exactly once, not that the
    # queue was otherwise empty.
    assert set(claimed_for_this_test) == set(task_ids)
    assert len(claimed_for_this_test) == len(task_ids)
    assert len(claimed) == len(set(claimed))
    assert {store.get_task(task_id)["status"] for task_id in task_ids} == {"completed"}

    resume_task_id = f"e2e-resume-{uuid4().hex}"
    store.create_task(resume_task_id, "resume", None, "waiting_review", input_state={"goal": "resume"})
    store.queue_task_resume(resume_task_id, {"paused_node_id": "review"}, "approved", "resume in e2e")
    resumed = store.get_task(resume_task_id)
    assert resumed["status"] == "queued"
    assert any(item["artifact_type"] == "workflow_checkpoint" for item in store.get_artifacts(resume_task_id))

    recovery_task_id = f"e2e-recovery-{uuid4().hex}"
    store.create_task(recovery_task_id, "recover", None, "queued")
    assert store.claim_task(recovery_task_id, "crashed-worker", lease_seconds=1)
    with store.connection() as connection:
        connection.execute(
            "UPDATE agent_task SET lease_until=NOW() - INTERVAL '1 second' WHERE task_id=%s",
            (recovery_task_id,),
        )
    assert recovery_task_id in store.recover_expired_task_ids()
    assert store.claim_task(recovery_task_id, "recovery-worker", lease_seconds=20)
    assert store.heartbeat_task(recovery_task_id, "recovery-worker", lease_seconds=20)
