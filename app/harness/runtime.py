from __future__ import annotations

import multiprocessing
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.core.config import settings
from app.core.security import execution_auth_context
from app.harness.context import AgentExecutionContext
from app.persistence.factory import get_persistence_stores

GraphRunner = Callable[[dict[str, Any]], dict[str, Any]]


class HarnessRuntime:

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jaycode-worker")
        self.futures: dict[str, Future[dict[str, Any]]] = {}
        self.processes: dict[str, multiprocessing.Process] = {}
    
    # 创建任务
    def create_context(
        self,
        goal: str,
        project_path: str | None = None,
        variables: dict[str, Any] | None = None,
        input_state: dict[str, Any] | None = None,
    ) -> AgentExecutionContext:
        context = AgentExecutionContext(goal=goal, project_path=project_path, variables=variables or {})# 创建上下文
        auth_context = execution_auth_context()
        context.variables.setdefault("request_id", auth_context.request_id)
        context.variables.setdefault("actor_id", auth_context.actor_id)
        context.variables.setdefault("role", auth_context.role)
        existing = get_persistence_stores().task.create_task(context.task_id, goal, project_path, "queued", {
            "request_id": auth_context.request_id,
            "actor_id": auth_context.actor_id,
            "role": auth_context.role,
            "idempotency_key": context.variables.get("idempotency_key"),
        }, input_state=input_state)# 任务信息落库
        if existing:
            context.task_id = str(existing["task_id"])
            context.status = str(existing.get("status") or "queued")
        else:
            context.status = "queued"
            event = context.events.emit(context.task_id, "task", "任务已加入队列", status="queued")
            get_persistence_stores().task.append_event(event.to_dict())
        return context

    def run_graph_async(self, context: AgentExecutionContext, graph_runner: GraphRunner, input_state: dict[str, Any]) -> Future[dict[str, Any]]:
        future = self.executor.submit(self.run_graph, context, graph_runner, input_state)
        self.futures[context.task_id] = future
        def timeout_guard() -> None:
            if not future.done():
                get_persistence_stores().task.update_task(context.task_id, "failed")
        timer = threading.Timer(max(1, settings.jaycode_task_max_runtime_seconds), timeout_guard)
        timer.daemon = True
        timer.start()
        future.add_done_callback(lambda _future: timer.cancel())
        return future

    def run_graph_process(self, context: AgentExecutionContext, graph_runner: GraphRunner) -> multiprocessing.Process:
        """Run a persisted task in an isolated local process."""
        process = multiprocessing.get_context("spawn").Process(
            target=_process_entry,
            args=(context.task_id, graph_runner),
            name=f"jaycode-task-{context.task_id[-8:]}",
            daemon=True,
        )
        self.processes[context.task_id] = process
        process.start()
        return process

    def cancel_task(self, task_id: str) -> bool:
        future = self.futures.get(task_id)
        cancelled = bool(future and future.cancel())
        process = self.processes.get(task_id)
        if process and process.is_alive():
            process.terminate()
            process.join(timeout=1)
            cancelled = True
        persisted = get_persistence_stores().task.cancel_task(task_id)
        return cancelled or persisted or get_persistence_stores().task.is_task_cancelled(task_id)

    # 运行并治理
    def run_graph(self, context: AgentExecutionContext, graph_runner: GraphRunner, input_state: dict[str, Any]) -> dict[str, Any]:
        # 1. 更新任务状态为 running
        context.status = "running"
        get_persistence_stores().task.update_task(context.task_id, "running")
        # 2. 记录开始事件
        event = context.events.emit(context.task_id, "task", "任务开始执行", status="running")
        get_persistence_stores().task.append_event(event.to_dict())
        try:
            if get_persistence_stores().task.is_task_cancelled(context.task_id) or get_persistence_stores().task.is_task_failed(context.task_id):
                return {"task_id": context.task_id, "status": "cancelled", "events": context.events.to_list(), "result": {}}
            # 3. 真正跑图
            result = graph_runner({**input_state, "task_id": context.task_id, "events": context.events.to_list()})
            if get_persistence_stores().task.is_task_cancelled(context.task_id) or get_persistence_stores().task.is_task_failed(context.task_id):
                context.status = "cancelled"
                return {"task_id": context.task_id, "status": "cancelled", "events": context.events.to_list(), "result": {}}
            # 4. 提取结果
            final_report = _extract_final_report(result)
            public_result = _public_result(result)
            context.status = _resolve_task_status(public_result)

            # 5. 构造持久化 Bundle，状态、产物和事件一次提交
            artifacts: list[tuple[str, str, Any]] = [("graph_result", "result", public_result)]
            if public_result.get("resume_checkpoint"):
                artifacts.append(("workflow_checkpoint", "resume", public_result["resume_checkpoint"]))
            governance_artifact = _governance_artifact(public_result)
            if governance_artifact:
                artifacts.append(("governance", "governance", governance_artifact))

            # 6. 合并事件
            graph_events = result.get("events", [])

             # 7. 判断最终状态
            final_message = "等待人工审核" if context.status == "waiting_review" else "任务执行完成"
            event = context.events.emit(context.task_id, "task", final_message, status=context.status)
            all_events = [graph_event for graph_event in graph_events if graph_event.get("task_id")] + [event.to_dict()]
            get_persistence_stores().task.save_task_bundle(context.task_id, context.status, final_report, artifacts, all_events)
            combined_events = context.events.to_list()[:-1] + graph_events + [event.to_dict()]
            return {
                "task_id": context.task_id,
                "status": context.status,
                "events": combined_events,
                "result": public_result,
            }
        except Exception as exc:
            # 8. 异常处理

            context.status = "failed"
            event = context.events.emit(context.task_id, "error", str(exc), status="failed")
            get_persistence_stores().task.save_task_bundle(
                context.task_id,
                "failed",
                None,
                [("error", "failure", {"error_code": "TASK_EXECUTION_FAILED", "message": str(exc)})],
                [event.to_dict()],
                error_code="TASK_EXECUTION_FAILED",
                error_message=str(exc),
            )
            raise


harness_runtime = HarnessRuntime()


def _process_entry(task_id: str, graph_runner: GraphRunner) -> None:
    worker_id = f"pid-{os.getpid()}"
    record = get_persistence_stores().task.claim_task(task_id, worker_id)
    if not record:
        return
    variables = get_persistence_stores().task.get_task_input(task_id)
    variables.update({
        "request_id": record.get("request_id"),
        "actor_id": record.get("actor_id") or "system-agent",
        "role": record.get("role") or "system-agent",
    })
    context = AgentExecutionContext(
        goal=str(record.get("goal") or ""),
        project_path=record.get("project_path"),
        task_id=task_id,
        variables=variables,
    )
    try:
        harness_runtime.run_graph(context, graph_runner, variables)
    except Exception:  # noqa: BLE001 - worker boundary must persist failure and exit quietly
        # run_graph persists the failed state and event; the worker must exit
        # without leaking a traceback to the parent API process.
        return


def _extract_final_report(result: dict[str, Any]) -> str | None:
    if "final_report" in result:
        return result["final_report"]
    nested = result.get("result")
    if isinstance(nested, dict):
        return nested.get("final_report") or nested.get("report_markdown")
    return None


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    nested = result.get("result")
    if isinstance(nested, dict):
        return nested
    return {
        "final_report": result.get("final_report"),
        "events": result.get("events", []),
    }


def _governance_artifact(public_result: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "governance",
        "risk_level",
        "review_required",
        "next_actions",
        "suggestion_records",
        "suggestions",
    ]
    artifact = {key: public_result.get(key) for key in keys if public_result.get(key) not in (None, [], {})}
    if "governance" not in artifact and any(key in artifact for key in ["risk_level", "review_required", "next_actions"]):
        artifact["governance"] = {
            "risk_level": artifact.get("risk_level", "low"),
            "review_required": bool(artifact.get("review_required")),
            "next_actions": artifact.get("next_actions", []),
            "suggestion_record_count": len(artifact.get("suggestion_records", [])),
        }
    return artifact


def _resolve_task_status(public_result: dict[str, Any]) -> str:
    review_packet = public_result.get("human_review_packet")
    if public_result.get("human_review_required") and review_packet:
        return "waiting_review"
    return "completed"
