"""Local persistent task worker.

Run with ``python -m app.harness.worker``.  The API only enqueues tasks;
this process owns task execution, leases, heartbeats and recovery.
"""

from __future__ import annotations

import argparse
import os
import threading
from typing import Any

from app.graphs.collaboration_runner import run_collaboration_task
from app.graphs.workflow_compiler import resume_task_workflow, run_task_workflow
from app.harness.context import AgentExecutionContext
from app.harness.runtime import harness_runtime
from app.persistence.sqlite_store import task_store


class LocalTaskWorker:
    def __init__(self, worker_id: str | None = None, poll_seconds: float = 1.0, lease_seconds: int = 30, max_attempts: int = 3) -> None:
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self.poll_seconds = max(0.1, poll_seconds)
        self.lease_seconds = max(2, lease_seconds)
        self.max_attempts = max(1, max_attempts)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> bool:
        task_store.recover_expired_task_ids()
        record = task_store.claim_next_task(self.worker_id, self.lease_seconds)
        if not record:
            return False
        if int(record.get("attempt") or 0) > self.max_attempts:
            task_id = record["task_id"]
            task_store.save_task_bundle(
                task_id, "failed", None,
                [("error", "failure", {"error_code": "WORKER_RETRY_LIMIT", "message": "Worker retry limit exceeded."})],
                [{"event_id": f"evt_retry_limit_{task_id}_{record.get('attempt')}", "task_id": task_id, "type": "worker_crashed", "status": "failed", "content": "Worker retry limit exceeded."}],
                error_code="WORKER_RETRY_LIMIT",
                error_message="Worker retry limit exceeded.",
            )
            return True
        self._run_record(record)
        return True

    def run_forever(self) -> None:
        task_store.register_worker(self.worker_id, os.getpid())
        try:
            while not self._stop.is_set():
                if not self.run_once():
                    task_store.heartbeat_worker(self.worker_id)
                    self._stop.wait(self.poll_seconds)
        finally:
            task_store.unregister_worker(self.worker_id)

    def _run_record(self, record: dict[str, Any]) -> None:
        task_id = str(record["task_id"])
        heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(max(1, self.lease_seconds // 3)):
                if not task_store.heartbeat_task(task_id, self.worker_id, self.lease_seconds):
                    return
                task_store.heartbeat_worker(self.worker_id, task_id)

        thread = threading.Thread(target=heartbeat, name=f"heartbeat-{task_id[-8:]}", daemon=True)
        thread.start()
        variables = task_store.get_task_input(task_id)
        variables.update({"request_id": record.get("request_id"), "actor_id": record.get("actor_id") or "system-agent", "role": record.get("role") or "system-agent"})
        runner_kind = variables.pop("_jaycode_runner", "workflow")
        if runner_kind == "collaboration":
            graph_runner = run_collaboration_task
        elif runner_kind == "resume":
            resume_payload = variables.pop("_resume_payload", {})
            checkpoint = resume_payload.get("checkpoint", {})
            action = str(resume_payload.get("action") or "approved")
            comment = resume_payload.get("comment")
            graph_runner = lambda _state: resume_task_workflow(checkpoint, action, comment)
        else:
            graph_runner = run_task_workflow
        context = AgentExecutionContext(goal=str(record.get("goal") or ""), project_path=record.get("project_path"), task_id=task_id, variables=variables)
        try:
            harness_runtime.run_graph(context, graph_runner, variables)
        except Exception as exc:  # noqa: BLE001 - worker boundary records failure in the runtime
            current = task_store.get_task(task_id)
            if current and current.get("status") == "running":
                task_store.save_task_bundle(
                    task_id,
                    "failed",
                    None,
                    [("error", "failure", {"error_code": "WORKER_EXECUTION_FAILED", "message": str(exc)})],
                    [{"event_id": f"evt_worker_failure_{task_id}_{record.get('attempt')}", "task_id": task_id, "type": "worker_crashed", "status": "failed", "content": "Worker execution failed."}],
                    error_code="WORKER_EXECUTION_FAILED",
                    error_message=str(exc),
                )
        finally:
            heartbeat_stop.set()
            thread.join(timeout=1)
            task_store.heartbeat_worker(self.worker_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Jaycode local task worker")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()
    LocalTaskWorker(worker_id=args.worker_id, poll_seconds=args.poll_seconds, lease_seconds=args.lease_seconds, max_attempts=args.max_attempts).run_forever()


if __name__ == "__main__":
    main()
