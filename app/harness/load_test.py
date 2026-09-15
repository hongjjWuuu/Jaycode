from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.persistence.sqlite_store import SQLiteTaskStore


def run_worker_load_test(db_path: str | Path, task_count: int = 100, worker_count: int = 2) -> dict[str, Any]:
    store = SQLiteTaskStore(db_path)
    enqueue_durations: list[float] = []
    for index in range(task_count):
        started = time.perf_counter()
        store.create_task(f"load-{uuid4().hex}", f"synthetic-{index}", None, "queued", input_state={"synthetic": True})
        enqueue_durations.append(time.perf_counter() - started)

    claim_durations: list[float] = []
    claimed: list[str] = []
    lock = threading.Lock()
    started = time.perf_counter()

    def consume(worker_number: int) -> None:
        worker_id = f"load-worker-{worker_number}"
        while True:
            claim_started = time.perf_counter()
            task = store.claim_next_task(worker_id, lease_seconds=30)
            if not task:
                return
            claim_durations.append(time.perf_counter() - claim_started)
            task_id = str(task["task_id"])
            with lock:
                claimed.append(task_id)
            store.save_task_bundle(
                task_id,
                "completed",
                "synthetic result",
                [("synthetic", "result", {"ok": True})],
                [{"event_id": f"load-event-{task_id}", "task_id": task_id, "type": "task", "status": "completed", "content": "done"}],
            )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(consume, index) for index in range(worker_count)]
        for future in futures:
            future.result()
    elapsed = time.perf_counter() - started
    tasks = store.list_tasks(limit=task_count)
    completed = sum(task.get("status") == "completed" for task in tasks)
    return {
        "task_count": task_count,
        "worker_count": worker_count,
        "claimed_count": len(claimed),
        "unique_claimed_count": len(set(claimed)),
        "completed_count": completed,
        "elapsed_seconds": elapsed,
        "throughput_tasks_per_second": task_count / elapsed if elapsed else 0,
        "enqueue_p95_ms": _p95(enqueue_durations) * 1000,
        "claim_p95_ms": _p95(claim_durations) * 1000,
    }


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
