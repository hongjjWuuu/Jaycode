from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.persistence.postgres_store import PostgresTaskStore

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL integration requires DATABASE_URL")


def test_postgres_schema_and_task_contract_are_idempotent() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    store.init_full_schema()
    task_id = f"pg-test-{uuid4().hex}"
    try:
        store.create_task(task_id, "contract test", None, "queued", {"idempotency_key": f"key-{task_id}"}, {"hello": "world"})
        assert store.get_task_input(task_id) == {"hello": "world"}
        claimed = store.claim_next_task(f"pg-worker-{uuid4().hex}", lease_seconds=20)
        assert claimed and claimed["task_id"] == task_id
        store.save_task_bundle(
            task_id,
            "completed",
            "done",
            [("contract", "result", {"ok": True})],
            [{"event_id": f"event-{task_id}", "task_id": task_id, "type": "task", "status": "completed", "content": "done"}],
        )
        assert store.get_task(task_id)["status"] == "completed"
        assert store.get_events_after(task_id)[0]["type"] == "task"
        assert store.get_artifacts(task_id)[0]["content"] == {"ok": True}
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM agent_task WHERE task_id=%s", (task_id,))
