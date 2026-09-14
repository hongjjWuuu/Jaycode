from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.core.config import settings
from app.core.security import execution_auth_context
from app.harness.context import AgentExecutionContext
from app.persistence.sqlite_store import task_store

GraphRunner = Callable[[dict[str, Any]], dict[str, Any]]


class HarnessRuntime:

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jaycode-worker")
        self.futures: dict[str, Future[dict[str, Any]]] = {}
    
    # 创建任务
    def create_context(
        self,
        goal: str,
        project_path: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> AgentExecutionContext:
        context = AgentExecutionContext(goal=goal, project_path=project_path, variables=variables or {})# 创建上下文
        auth_context = execution_auth_context()
        context.variables.setdefault("request_id", auth_context.request_id)
        context.variables.setdefault("actor_id", auth_context.actor_id)
        context.variables.setdefault("role", auth_context.role)
        task_store.create_task(context.task_id, goal, project_path, "created", {
            "request_id": auth_context.request_id,
            "actor_id": auth_context.actor_id,
            "role": auth_context.role,
            "idempotency_key": context.variables.get("idempotency_key"),
        })# 任务信息落库
        event = context.events.emit(context.task_id, "task", "任务已创建", status="created") # 记录事件
        task_store.append_event(event.to_dict())# 事件落库
        return context

    def run_graph_async(self, context: AgentExecutionContext, graph_runner: GraphRunner, input_state: dict[str, Any]) -> Future[dict[str, Any]]:
        future = self.executor.submit(self.run_graph, context, graph_runner, input_state)
        self.futures[context.task_id] = future
        def timeout_guard() -> None:
            if not future.done():
                task_store.update_task(context.task_id, "failed")
        timer = threading.Timer(max(1, settings.jaycode_task_max_runtime_seconds), timeout_guard)
        timer.daemon = True
        timer.start()
        future.add_done_callback(lambda _future: timer.cancel())
        return future

    def cancel_task(self, task_id: str) -> bool:
        future = self.futures.get(task_id)
        cancelled = bool(future and future.cancel())
        task_store.update_task(task_id, "cancelled")
        return cancelled or task_store.is_task_cancelled(task_id)

    # 运行并治理
    def run_graph(self, context: AgentExecutionContext, graph_runner: GraphRunner, input_state: dict[str, Any]) -> dict[str, Any]:
        # 1. 更新任务状态为 running
        context.status = "running"
        task_store.update_task(context.task_id, "running")
        # 2. 记录开始事件
        event = context.events.emit(context.task_id, "task", "任务开始执行", status="running")
        task_store.append_event(event.to_dict())
        try:
            if task_store.is_task_cancelled(context.task_id) or task_store.is_task_failed(context.task_id):
                return {"task_id": context.task_id, "status": "cancelled", "events": context.events.to_list(), "result": {}}
            # 3. 真正跑图
            result = graph_runner({**input_state, "task_id": context.task_id, "events": context.events.to_list()})
            if task_store.is_task_cancelled(context.task_id) or task_store.is_task_failed(context.task_id):
                context.status = "cancelled"
                return {"task_id": context.task_id, "status": "cancelled", "events": context.events.to_list(), "result": {}}
            # 4. 提取结果
            final_report = _extract_final_report(result)
            public_result = _public_result(result)
            context.status = _resolve_task_status(public_result)

            # 5. 持久化
            task_store.save_artifact(context.task_id, "graph_result", "result", public_result)# 保存图执行结果
            if public_result.get("resume_checkpoint"):
                task_store.save_artifact(context.task_id, "workflow_checkpoint", "resume", public_result["resume_checkpoint"])# 保存断点
            governance_artifact = _governance_artifact(public_result)
            if governance_artifact:
                task_store.save_artifact(context.task_id, "governance", "governance", governance_artifact)# 保存治理信息
            task_store.update_task(context.task_id, context.status, final_report) # 更新任务状态

            # 6. 合并事件
            graph_events = result.get("events", [])
            for graph_event in graph_events:
                if graph_event.get("task_id"):
                    task_store.append_event(graph_event)

             # 7. 判断最终状态
            final_message = "等待人工审核" if context.status == "waiting_review" else "任务执行完成"
            event = context.events.emit(context.task_id, "task", final_message, status=context.status)
            task_store.append_event(event.to_dict())
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
            task_store.update_task(context.task_id, "failed")
            event = context.events.emit(context.task_id, "error", str(exc), status="failed")
            task_store.append_event(event.to_dict())
            raise


harness_runtime = HarnessRuntime()


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
