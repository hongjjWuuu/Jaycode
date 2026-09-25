"""Read-only operational state assembled from existing runtime and store data."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.harness.supervisor import worker_supervisor
from app.persistence.factory import get_persistence_stores


def _as_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    """Return operational metadata only; goals and project paths stay private."""
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


class OperationsService:
    """Build a bounded, low-cardinality snapshot for the admin operations view."""

    def overview(self) -> dict[str, Any]:
        stores = get_persistence_stores()
        now = datetime.now(UTC)
        database_ready = True
        try:
            stores.ping()
        except Exception:  # noqa: BLE001 - detail must not reach the operations payload
            database_ready = False

        tasks = stores.task.list_tasks(limit=1_000)
        workers = stores.task.list_workers()
        status_counts = Counter(str(task.get("status") or "unknown") for task in tasks)
        queued = [task for task in tasks if task.get("status") == "queued"]
        waiting_review = [task for task in tasks if task.get("status") == "waiting_review"]
        failed = [task for task in tasks if task.get("status") == "failed"]
        queued.sort(key=lambda task: str(task.get("created_at") or ""))
        failed.sort(key=lambda task: str(task.get("updated_at") or ""), reverse=True)
        oldest_queued = queued[0] if queued else None
        oldest_created = _as_utc(oldest_queued.get("created_at")) if oldest_queued else None
        supervisor = worker_supervisor.snapshot()
        active_registered_workers = sum(worker.get("status") == "running" for worker in workers)
        has_worker = bool(active_registered_workers or supervisor["active_workers"])

        alerts: list[dict[str, str]] = []
        if not database_ready:
            alerts.append({"code": "DATABASE_NOT_READY", "severity": "critical", "message": "数据库未就绪。"})
        if supervisor["status"] == "degraded":
            alerts.append({"code": "WORKER_DEGRADED", "severity": "critical", "message": "Worker Supervisor 已降级。"})
        if queued and not has_worker:
            alerts.append({"code": "QUEUED_WITHOUT_WORKER", "severity": "warning", "message": "存在排队任务但没有运行中的 Worker。"})
        if oldest_created and (now - oldest_created).total_seconds() >= settings.jaycode_operations_stale_queue_seconds:
            alerts.append({"code": "STALE_QUEUE", "severity": "warning", "message": "最早排队任务已超过运营阈值。"})
        if failed:
            alerts.append({"code": "RECENT_TASK_FAILURE", "severity": "warning", "message": "存在最近失败的任务。"})

        return {
            "generated_at": now.isoformat(),
            "readiness": {"database": database_ready, "supervisor": bool(supervisor["alive"])},
            "supervisor": supervisor,
            "workers": [
                {"worker_id": worker.get("worker_id"), "status": worker.get("status"), "last_heartbeat": worker.get("last_heartbeat")}
                for worker in workers
            ],
            "task_counts": dict(sorted(status_counts.items())),
            "oldest_queued_task": _task_summary(oldest_queued) if oldest_queued else None,
            "waiting_review": [_task_summary(task) for task in waiting_review[: settings.jaycode_operations_failed_task_limit]],
            "recent_failed": [_task_summary(task) for task in failed[: settings.jaycode_operations_failed_task_limit]],
            "alerts": alerts,
        }
