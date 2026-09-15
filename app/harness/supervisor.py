from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from app.core.observability import metrics

logger = logging.getLogger("jaycode.supervisor")


class WorkerSupervisor:
    def __init__(self, *, max_restarts: int = 5, backoff_seconds: float = 2.0) -> None:
        self.max_restarts = max(1, max_restarts)
        self.backoff_seconds = max(0.1, backoff_seconds)
        self.worker_count = 1
        self.processes: dict[int, subprocess.Popen[Any]] = {}
        self.restart_counts: dict[int, int] = {}
        self.next_start_at: dict[int, float] = {}
        self.status = "stopped"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def process(self) -> subprocess.Popen[Any] | None:
        return self.processes.get(0)

    @property
    def restart_count(self) -> int:
        return sum(self.restart_counts.values())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.status = "starting"
        self._thread = threading.Thread(target=self._watch, name="jaycode-worker-supervisor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        self.status = "stopped"

    def snapshot(self) -> dict[str, Any]:
        alive = sum(process.poll() is None for process in self.processes.values())
        return {
            "status": self.status,
            "worker_count": self.worker_count,
            "active_workers": alive,
            "pids": [process.pid for process in self.processes.values() if process.poll() is None],
            "restart_count": self.restart_count,
            "restart_counts": dict(self.restart_counts),
            "alive": alive == self.worker_count and self.status not in {"degraded", "stopped"},
        }

    def _watch(self) -> None:
        import time

        while not self._stop.is_set():
            now = time.monotonic()
            for slot in range(self.worker_count):
                process = self.processes.get(slot)
                if process and process.poll() is not None:
                    code = process.returncode
                    del self.processes[slot]
                    self.restart_counts[slot] = self.restart_counts.get(slot, 0) + 1
                    metrics.inc("jaycode_worker_restarts_total")
                    logger.error("worker_exit", extra={"worker_id": f"supervised-{slot}", "error_code": "WORKER_EXIT", "status": str(code)})
                    self.next_start_at[slot] = now + self.backoff_seconds * min(self.restart_counts[slot], 5)
                if slot not in self.processes and self.restart_counts.get(slot, 0) < self.max_restarts and now >= self.next_start_at.get(slot, 0):
                    self.processes[slot] = subprocess.Popen(
                        [sys.executable, "-m", "app.harness.worker", "--worker-id", f"supervised-{slot}"],
                        cwd=str(Path.cwd()), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    metrics.inc("jaycode_workers_started_total")
            degraded = any(count >= self.max_restarts for count in self.restart_counts.values())
            self.status = "degraded" if degraded else "running" if len(self.processes) == self.worker_count else "backoff"
            alive = sum(process.poll() is None for process in self.processes.values())
            metrics.set("jaycode_workers", alive)
            metrics.set("jaycode_worker_supervisor_ready", int(alive == self.worker_count and not degraded))
            self._stop.wait(0.5)


worker_supervisor = WorkerSupervisor()
