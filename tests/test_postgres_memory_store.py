from __future__ import annotations

from uuid import uuid4

import pytest
from postgres_test_config import isolated_postgres_url

from app.persistence.postgres_memory_store import PostgresMemoryStore

DATABASE_URL = isolated_postgres_url()
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DATABASE_URL, reason="set JAYCODE_TEST_DATABASE_URL to an isolated local test database"),
]


def test_postgres_memory_lifecycle_and_duplicate_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.persistence.memory_store as memory_module

    store = PostgresMemoryStore(DATABASE_URL)
    store.init_schema()
    store.init_schema()
    content = f"contract fact {uuid4().hex}"
    candidate = {
        "memory_type": "project_fact",
        "memory_key": f"key-{uuid4().hex}",
        "content": content,
        "confidence": 0.9,
    }
    monkeypatch.setattr(memory_module, "_extract_memory_candidates", lambda _: ([candidate], "rule"))
    memory_id = ""
    try:
        created = store.extract_candidates(
            content,
            scope="project",
            scope_id="pg-contract",
            source_ref="contract-test",
            actor_id="pg-contract-actor",
        )
        assert len(created) == 1
        memory_id = created[0]["memory_id"]
        assert store.get_memory(memory_id)["content"] == content
        duplicate = store.extract_candidates(content, scope="project", scope_id="pg-contract")
        assert duplicate[0]["duplicate"] is True
        confirmed = store.confirm(memory_id, "memory/contract", actor_id="pg-contract-reviewer")
        assert confirmed and confirmed["status"] == "confirmed"
        events = store.list_lifecycle_events(memory_id)
        assert [event["action"] for event in events] == ["created", "confirmed"]
        assert store.delete(memory_id, actor_id="pg-contract-admin") is True
        assert store.get_memory(memory_id) is None
        assert [event["action"] for event in store.list_lifecycle_events(memory_id)] == ["created", "confirmed", "deleted"]
    finally:
        if memory_id:
            with store._connect() as conn:
                conn.execute("DELETE FROM memory_lifecycle_event WHERE memory_id=%s", (memory_id,))
                conn.execute("DELETE FROM memory_record WHERE memory_id=%s", (memory_id,))


def test_postgres_audit_and_worker_registry_contract() -> None:
    from app.persistence.postgres_store import PostgresTaskStore

    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    worker_id = f"pg-worker-{uuid4().hex}"
    request_id = f"pg-request-{uuid4().hex}"
    audit = store.save_security_audit(
        {
            "request_id": request_id,
            "actor_id": "contract-actor",
            "role": "admin",
            "action": "contract_probe",
            "resource_type": "test",
            "resource_id": worker_id,
            "status": "completed",
            "metadata": {"safe": True},
        }
    )
    try:
        store.register_worker(worker_id, 12345)
        store.heartbeat_worker(worker_id, "task-contract")
        workers = store.list_workers()
        worker = next(item for item in workers if item["worker_id"] == worker_id)
        assert worker["active_task_id"] == "task-contract"
        audits = store.list_security_audits(actor_id="contract-actor", action="contract_probe")
        assert audits[0]["audit_id"] == audit["audit_id"]
        assert audits[0]["metadata"] == {"safe": True}
        store.unregister_worker(worker_id)
        stopped = next(item for item in store.list_workers() if item["worker_id"] == worker_id)
        assert stopped["status"] == "stopped"
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM security_audit_log WHERE audit_id=%s", (audit["audit_id"],))
            conn.execute("DELETE FROM agent_worker WHERE worker_id=%s", (worker_id,))
