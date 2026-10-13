from __future__ import annotations

from app.persistence.sqlite_store import SQLiteTaskStore


def test_terminal_task_can_be_soft_deleted_and_restored(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "recycle.sqlite3")
    store.create_task("done", "done", ".", "completed", {"actor_id": "owner"})
    store.save_artifact("done", "result", "result", {"final_report": "keep me"})

    deleted = store.soft_delete_tasks(["done"], "owner", False)
    assert deleted["deleted"] and store.get_task("done") is None
    assert store.list_tasks() == []
    assert store.list_tasks(include_deleted=True)[0]["task_id"] == "done"

    restored = store.restore_deleted_tasks(["done"], "owner", False)
    assert restored["restored"] == [{"task_id": "done"}]
    assert store.get_task("done") is not None
    assert store.get_artifacts("done")[0]["content"]["final_report"] == "keep me"


def test_task_delete_enforces_terminal_status_and_owner(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "permissions.sqlite3")
    store.create_task("running", "run", ".", "running", {"actor_id": "another"})
    store.create_task("other", "other", ".", "completed", {"actor_id": "owner"})

    result = store.soft_delete_tasks(["running", "other"], "another", False)
    assert {item["error_code"] for item in result["skipped"]} == {"TASK_DELETE_NOT_TERMINAL", "TASK_DELETE_FORBIDDEN"}


def test_expired_soft_deleted_task_purges_task_private_records(tmp_path) -> None:
    store = SQLiteTaskStore(tmp_path / "purge.sqlite3")
    store.create_task("expired", "expired", ".", "completed", {"actor_id": "owner"})
    store.save_artifact("expired", "result", "result", {"value": 1})
    store.soft_delete_tasks(["expired"], "owner", False)
    with store._connect() as conn:
        conn.execute("UPDATE agent_task SET purge_after = ? WHERE task_id = ?", ("2000-01-01T00:00:00+08:00", "expired"))

    assert store.purge_expired_deleted_tasks() == ["expired"]
    assert store.get_task("expired", include_deleted=True) is None
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_task_artifact WHERE task_id = ?", ("expired",)).fetchone()[0] == 0
