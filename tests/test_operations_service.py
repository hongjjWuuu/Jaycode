from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.operations_service import OperationsService


class _TaskStore:
    def list_tasks(self, limit: int = 1000):
        del limit
        now = datetime.now(UTC)
        return [
            {"task_id": "queued-old", "status": "queued", "created_at": (now - timedelta(minutes=10)).isoformat(), "updated_at": now.isoformat(), "goal": "private", "project_path": "D:/secret"},
            {"task_id": "failed-new", "status": "failed", "created_at": now.isoformat(), "updated_at": now.isoformat(), "goal": "private"},
            {"task_id": "review", "status": "waiting_review", "created_at": now.isoformat(), "updated_at": now.isoformat()},
        ]

    def list_workers(self):
        return []


class _Stores:
    task = _TaskStore()

    def ping(self):
        return None


def test_operations_overview_is_bounded_and_redacts_task_content(monkeypatch) -> None:
    import app.services.operations_service as operations

    monkeypatch.setattr(operations, "get_persistence_stores", lambda: _Stores())
    monkeypatch.setattr(operations.worker_supervisor, "snapshot", lambda: {
        "status": "stopped", "worker_count": 1, "active_workers": 0, "restart_count": 0, "alive": False,
    })
    result = OperationsService().overview()

    assert result["task_counts"] == {"failed": 1, "queued": 1, "waiting_review": 1}
    assert {alert["code"] for alert in result["alerts"]} >= {"QUEUED_WITHOUT_WORKER", "STALE_QUEUE", "RECENT_TASK_FAILURE"}
    assert result["oldest_queued_task"] == {"task_id": "queued-old", "status": "queued", "created_at": result["oldest_queued_task"]["created_at"], "updated_at": result["oldest_queued_task"]["updated_at"]}
    assert "goal" not in str(result)
    assert "D:/secret" not in str(result)


def test_operations_route_requires_admin_role() -> None:
    from app.core.security import required_role

    assert required_role("GET", "/api/v1/operations/overview") == "admin"
