from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.harness.events import BEIJING_TZ, utc_now_iso
from app.persistence.sqlite_path import resolve_sqlite_path

TASK_TRANSITIONS: dict[str, set[str]] = {
    "created": {"queued", "running", "cancelled", "failed"},
    "queued": {"running", "cancelled", "failed"},
    "running": {"completed", "waiting_review", "paused", "failed", "cancelled", "queued"},
    "waiting_review": {"running", "queued", "completed", "cancelled", "rejected", "paused"},
    "paused": {"queued", "running", "cancelled", "failed"},
    "failed": {"queued", "running"},
    "completed": set(),
    "cancelled": {"queued"},
    "rejected": set(),
}

# 这个文件不是简单的数据层，而是整个项目的“事实仓库”。  
# 它把任务、事件、产物、工作流、技能、MCP、LLM、Benchmark 都存到同一个治理型数据库里。

class SQLiteTaskStore:

    # 初始化数据库路径
    # 创建目录
    # 初始化全部表结构
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = resolve_sqlite_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # 任务本体
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_task (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    project_path TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    final_report TEXT
                )
                """
            )
            self._ensure_column(conn, "agent_task", "request_id", "TEXT")
            self._ensure_column(conn, "agent_task", "actor_id", "TEXT")
            self._ensure_column(conn, "agent_task", "role", "TEXT")
            self._ensure_column(conn, "agent_task", "idempotency_key", "TEXT")
            self._ensure_column(conn, "agent_task", "execution_version", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "agent_task", "retry_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "agent_task", "resume_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "agent_task", "input_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "agent_task", "worker_id", "TEXT")
            self._ensure_column(conn, "agent_task", "lease_until", "TEXT")
            self._ensure_column(conn, "agent_task", "heartbeat_at", "TEXT")
            self._ensure_column(conn, "agent_task", "attempt", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "agent_task", "error_code", "TEXT")
            self._ensure_column(conn, "agent_task", "error_message", "TEXT")
            self._ensure_column(conn, "agent_task", "failed_at", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_queue ON agent_task(status, lease_until, created_at)")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS agent_worker (
                    worker_id TEXT PRIMARY KEY, pid INTEGER NOT NULL, started_at TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL, status TEXT NOT NULL, active_task_id TEXT,
                    restart_count INTEGER NOT NULL DEFAULT 0
                )"""
            )
            # 任务事件流
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_task_event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    node TEXT,
                    agent TEXT,
                    status TEXT,
                    content TEXT,
                    data_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 任务产物
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_task_artifact (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 工作流定义
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_definition (
                    workflow_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    nodes_json TEXT NOT NULL,
                    edges_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # 人工审核动作
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS human_review_action (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 学习计划
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_plan (
                    plan_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    quiz_json TEXT NOT NULL,
                    report_markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # LLM 调用 trace
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_call_trace (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model TEXT,
                    input_json TEXT,
                    output_text TEXT,
                    fallback_used INTEGER NOT NULL,
                    error_message TEXT,
                    latency_ms INTEGER NOT NULL,
                    token_usage_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "llm_call_trace", "request_id", "TEXT")
            self._ensure_column(conn, "llm_call_trace", "actor_id", "TEXT")
            self._ensure_column(conn, "llm_call_trace", "role", "TEXT")
            # prompt 版本
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_prompt_version (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    prompt_family TEXT NOT NULL DEFAULT '',
                    prompt_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    system_suffix TEXT,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(agent, prompt_version)
                )
                """
            )
            self._ensure_column(conn, "llm_prompt_version", "prompt_family", "TEXT NOT NULL DEFAULT ''")
            # MCP server 配置
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_server_config (
                    server_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    command TEXT,
                    args_json TEXT,
                    env_json TEXT,
                    url TEXT,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # MCP 工具注册
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_tool_registry (
                    tool_id TEXT PRIMARY KEY,
                    server_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    input_schema_json TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'available',
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(server_id, name)
                )
                """
            )
            # MCP 审批
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_tool_approval (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_code TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(agent_code, server_id, tool_name)
                )
                """
            )
            # MCP 调用日志
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_tool_call_log (
                    call_id TEXT PRIMARY KEY,
                    server_id TEXT,
                    tool_name TEXT NOT NULL,
                    agent_code TEXT,
                    input_json TEXT,
                    output_json TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    latency_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "agent_task_event", "event_seq", "INTEGER")
            self._ensure_column(conn, "agent_task_event", "execution_version", "INTEGER NOT NULL DEFAULT 1")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_event_task_created ON agent_task_event(task_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_event_event_id ON agent_task_event(event_id)")
            self._ensure_column(conn, "mcp_tool_call_log", "request_id", "TEXT")
            self._ensure_column(conn, "mcp_tool_call_log", "actor_id", "TEXT")
            self._ensure_column(conn, "mcp_tool_call_log", "role", "TEXT")
            self._ensure_column(conn, "mcp_tool_call_log", "command_summary", "TEXT")
            self._ensure_column(conn, "mcp_tool_call_log", "exit_code", "INTEGER")
            # Benchmark 运行记录
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_run (
                    run_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    benchmark_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Benchmark 结果记录
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_result (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    server_id TEXT,
                    tool_name TEXT,
                    iteration INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    error_message TEXT,
                    input_json TEXT,
                    output_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Skill 插件包
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_plugin (
                    plugin_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    author TEXT,
                    description TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    installed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Skill 注册表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_registry (
                    skill_code TEXT PRIMARY KEY,
                    plugin_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    execution_type TEXT NOT NULL,
                    permissions_json TEXT,
                    permission_levels_json TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    input_schema_json TEXT,
                    output_schema_json TEXT,
                    default_input_json TEXT,
                    dependencies_json TEXT,
                    tests_json TEXT,
                    version TEXT NOT NULL DEFAULT '1.0.0',
                    entrypoint TEXT,
                    source_format TEXT NOT NULL DEFAULT 'plugin_json',
                    contract_json TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "skill_registry", "default_input_json", "TEXT")
            self._ensure_column(conn, "skill_registry", "permission_levels_json", "TEXT")
            self._ensure_column(conn, "skill_registry", "risk_level", "TEXT NOT NULL DEFAULT 'low'")
            self._ensure_column(conn, "skill_registry", "dependencies_json", "TEXT")
            self._ensure_column(conn, "skill_registry", "tests_json", "TEXT")
            self._ensure_column(conn, "skill_registry", "version", "TEXT NOT NULL DEFAULT '1.0.0'")
            self._ensure_column(conn, "skill_registry", "entrypoint", "TEXT")
            self._ensure_column(conn, "skill_registry", "source_format", "TEXT NOT NULL DEFAULT 'plugin_json'")
            self._ensure_column(conn, "skill_registry", "contract_json", "TEXT")
            # Skill 审批
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_approval (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_code TEXT NOT NULL,
                    agent_code TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(skill_code, agent_code)
                )
                """
            )
            # Skill 执行日志
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_execution_log (
                    log_id TEXT PRIMARY KEY,
                    skill_code TEXT NOT NULL,
                    agent_code TEXT,
                    task_id TEXT,
                    input_json TEXT,
                    output_json TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    latency_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "skill_execution_log", "request_id", "TEXT")
            self._ensure_column(conn, "skill_execution_log", "actor_id", "TEXT")
            self._ensure_column(conn, "skill_execution_log", "role", "TEXT")
            # Skill 版本快照
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_version_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_code TEXT NOT NULL,
                    plugin_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(skill_code, version)
                )
                """
            )
            # Marketplace 安装记录
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plugin_marketplace_install (
                    install_id TEXT PRIMARY KEY,
                    package_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    package_type TEXT NOT NULL,
                    version TEXT,
                    source_url TEXT,
                    status TEXT NOT NULL,
                    summary_json TEXT,
                    manifest_json TEXT,
                    error_message TEXT,
                    installed_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "agent_task_artifact", "execution_version", "INTEGER NOT NULL DEFAULT 1")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_artifact_task_created ON agent_task_artifact(task_id, created_at)")
            self._ensure_column(conn, "plugin_marketplace_install", "approval_status", "TEXT NOT NULL DEFAULT 'approved'")
            self._ensure_column(conn, "plugin_marketplace_install", "approved_by", "TEXT")
            self._ensure_column(conn, "plugin_marketplace_install", "approved_at", "TEXT")
            self._ensure_column(conn, "plugin_marketplace_install", "approval_reason", "TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS security_audit_log (
                    audit_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT,
                    status TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    # 不是“简单建表”，而是考虑了 schema 演进 这说明项目已经把“版本兼容”当成架构的一部分。
    # 四个方法构成了任务治理的基础动作： 创建任务 更新状态 写事件 存产物
    def create_task(self, task_id: str, goal: str, project_path: str | None, status: str, context: dict[str, Any] | None = None, input_state: dict[str, Any] | None = None) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as conn:
            idempotency_key = (context or {}).get("idempotency_key")
            if idempotency_key:
                existing = conn.execute("SELECT * FROM agent_task WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if existing:
                    return dict(existing)
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_task(task_id, goal, project_path, status, created_at, updated_at, request_id, actor_id, role, idempotency_key, execution_version, retry_count, resume_count, input_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, goal, project_path, status, now, now, (context or {}).get("request_id"), (context or {}).get("actor_id"), (context or {}).get("role"), idempotency_key, 1, 0, 0, json.dumps(input_state or {}, ensure_ascii=False)),
            )
        return None

    def save_security_audit(self, record: dict[str, Any]) -> dict[str, Any]:
        audit = {
            "audit_id": record.get("audit_id") or f"audit_{uuid4().hex}",
            "request_id": str(record.get("request_id") or ""),
            "actor_id": str(record.get("actor_id") or "unknown"),
            "role": str(record.get("role") or "unknown"),
            "action": str(record.get("action") or "unknown"),
            "resource_type": str(record.get("resource_type") or "api"),
            "resource_id": str(record.get("resource_id") or ""),
            "status": str(record.get("status") or "unknown"),
            "metadata": record.get("metadata") or {},
            "created_at": record.get("created_at") or utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO security_audit_log(
                    audit_id, request_id, actor_id, role, action, resource_type,
                    resource_id, status, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit["audit_id"],
                    audit["request_id"],
                    audit["actor_id"],
                    audit["role"],
                    audit["action"],
                    audit["resource_type"],
                    audit["resource_id"],
                    audit["status"],
                    json.dumps(audit["metadata"], ensure_ascii=False),
                    audit["created_at"],
                ),
            )
        return audit

    def list_security_audits(
        self, limit: int = 100, actor_id: str | None = None, role: str | None = None,
        action: str | None = None, status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for field, value in (("actor_id", actor_id), ("role", role), ("action", action), ("status", status)):
            if value:
                clauses.append(f"{field} = ?")
                params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 1000)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM security_audit_log{where} ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

    def update_task(self, task_id: str, status: str, final_report: str | None = None, *, retry: bool = False, resume: bool = False) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            current = conn.execute("SELECT status FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
            if current and status != current["status"] and status not in TASK_TRANSITIONS.get(current["status"], set()):
                raise ValueError(f"Invalid task status transition: {current['status']} -> {status}")
            conn.execute(
                """
                UPDATE agent_task
                SET status = ?, final_report = COALESCE(?, final_report), updated_at = ?,
                    retry_count = retry_count + ?, resume_count = resume_count + ?,
                    execution_version = execution_version + 1,
                    worker_id = CASE WHEN ? IN ('completed', 'failed', 'cancelled', 'paused') THEN NULL ELSE worker_id END,
                    lease_until = CASE WHEN ? IN ('completed', 'failed', 'cancelled', 'paused') THEN NULL ELSE lease_until END,
                    heartbeat_at = CASE WHEN ? IN ('completed', 'failed', 'cancelled', 'paused') THEN NULL ELSE heartbeat_at END
                WHERE task_id = ?
                """,
                (status, final_report, now, int(retry), int(resume), status, status, status, task_id),
            )

    def append_event(self, event: dict[str, Any]) -> None:
        event_id = event.get("event_id") or f"evt_{event['task_id']}_{event.get('node') or 'event'}_{utc_now_iso()}"
        with self._connect() as conn:
            existing = conn.execute("SELECT 1 FROM agent_task_event WHERE event_id = ?", (event_id,)).fetchone()
            if existing:
                return
            sequence = conn.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM agent_task_event WHERE task_id = ?", (event["task_id"],)).fetchone()[0]
            conn.execute(
                """
                INSERT INTO agent_task_event(
                    event_id, task_id, event_type, node, agent, status, content, data_json, created_at, event_seq, execution_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event["task_id"],
                    event.get("type", "event"),
                    event.get("node"),
                    event.get("agent"),
                    event.get("status"),
                    event.get("content"),
                    json.dumps(event.get("data", {}), ensure_ascii=False),
                    event.get("timestamp") or utc_now_iso(),
                    sequence,
                    int(event.get("execution_version") or 1),
                ),
            )

    def save_artifact(self, task_id: str, artifact_type: str, name: str, content: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_task_artifact(task_id, artifact_type, name, content_json, created_at, execution_version)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, artifact_type, name, json.dumps(content, ensure_ascii=False), utc_now_iso(), 1),
            )

    def save_task_bundle(
        self,
        task_id: str,
        status: str,
        final_report: str | None,
        artifacts: list[tuple[str, str, Any]],
        events: list[dict[str, Any]],
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Atomically persist task state, artifacts and events for one execution."""
        now = utc_now_iso()
        with self._connect() as conn:
            current = conn.execute("SELECT status FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
            if not current:
                raise ValueError(f"Task `{task_id}` does not exist.")
            if status != current["status"] and status not in TASK_TRANSITIONS.get(current["status"], set()):
                raise ValueError(f"Invalid task status transition: {current['status']} -> {status}")
            conn.execute(
                "UPDATE agent_task SET status = ?, final_report = COALESCE(?, final_report), updated_at = ?, execution_version = execution_version + 1, worker_id = NULL, lease_until = NULL, heartbeat_at = NULL, error_code = ?, error_message = ?, failed_at = ? WHERE task_id = ?",
                (status, final_report, now, error_code if status == "failed" else None, error_message if status == "failed" else None, now if status == "failed" else None, task_id),
            )
            version = conn.execute("SELECT execution_version FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
            execution_version = int(version[0] if version else 1)
            for artifact_type, name, content in artifacts:
                conn.execute(
                    "INSERT INTO agent_task_artifact(task_id, artifact_type, name, content_json, created_at, execution_version) VALUES (?, ?, ?, ?, ?, ?)",
                    (task_id, artifact_type, name, json.dumps(content, ensure_ascii=False), now, execution_version),
                )
            for event in events:
                event_id = event.get("event_id") or f"evt_{task_id}_{event.get('node') or 'event'}_{utc_now_iso()}"
                if conn.execute("SELECT 1 FROM agent_task_event WHERE event_id = ?", (event_id,)).fetchone():
                    continue
                sequence = conn.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM agent_task_event WHERE task_id = ?", (task_id,)).fetchone()[0]
                conn.execute(
                    "INSERT INTO agent_task_event(event_id, task_id, event_type, node, agent, status, content, data_json, created_at, event_seq, execution_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_id, task_id, event.get("type", "event"), event.get("node"), event.get("agent"), event.get("status"), event.get("content"), json.dumps(event.get("data", {}), ensure_ascii=False), event.get("timestamp") or now, sequence, execution_version),
                )

    def cancel_task(self, task_id: str) -> bool:
        now = utc_now_iso()
        event_id = f"evt_{uuid4().hex}"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status, execution_version FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
            if not row or row["status"] in {"completed", "failed", "cancelled", "rejected"}:
                return False
            if "cancelled" not in TASK_TRANSITIONS.get(row["status"], set()):
                raise ValueError(f"Invalid task status transition: {row['status']} -> cancelled")
            conn.execute("UPDATE agent_task SET status = 'cancelled', updated_at = ?, worker_id = NULL, lease_until = NULL, heartbeat_at = NULL, execution_version = execution_version + 1 WHERE task_id = ?", (now, task_id))
            sequence = conn.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM agent_task_event WHERE task_id = ?", (task_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO agent_task_event(event_id, task_id, event_type, status, content, data_json, created_at, event_seq, execution_version) VALUES (?, ?, 'task_cancelled', 'cancelled', 'Task cancellation requested.', '{}', ?, ?, ?)",
                (event_id, task_id, now, sequence, int(row["execution_version"]) + 1),
            )
        return True

    def queue_task_resume(
        self, task_id: str, checkpoint: dict[str, Any], action: str, comment: str | None,
    ) -> None:
        """Atomically record reviewer action and enqueue checkpoint continuation."""
        row = self.get_task(task_id)
        if not row:
            raise ValueError(f"Task `{task_id}` does not exist.")
        if row["status"] != "waiting_review":
            raise ValueError(f"Task `{task_id}` is not waiting for review.")
        task_input = self.get_task_input(task_id)
        task_input["_jaycode_runner"] = "resume"
        task_input["_resume_payload"] = {"checkpoint": checkpoint, "action": action, "comment": comment}
        self.apply_review_transition(
            task_id,
            action,
            comment,
            "queued",
            [{
                "event_id": f"evt_{uuid4().hex}",
                "type": "human_review",
                "node": str(checkpoint.get("paused_node_id") or "human_review"),
                "status": "queued",
                "content": f"Review action {action} queued for resume.",
                "data": {"action": action, "resume": True},
            }],
            checkpoint=checkpoint,
            resume_input=task_input,
        )

    def apply_review_transition(
        self,
        task_id: str,
        action: str,
        comment: str | None,
        status: str,
        events: list[dict[str, Any]],
        *,
        checkpoint: dict[str, Any] | None = None,
        retry: bool = False,
        resume_input: dict[str, Any] | None = None,
    ) -> None:
        """Atomically persist a review decision and its task/checkpoint effects."""
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, execution_version FROM agent_task WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Task `{task_id}` does not exist.")
            current_status = str(row["status"])
            if status != current_status and status not in TASK_TRANSITIONS.get(current_status, set()):
                raise ValueError(f"Invalid task status transition: {current_status} -> {status}")

            version = int(row["execution_version"]) + 1
            conn.execute(
                "UPDATE agent_task SET status = ?, updated_at = ?, execution_version = ?, retry_count = retry_count + ?, resume_count = resume_count + ?, input_json = COALESCE(?, input_json), worker_id = CASE WHEN ? = 1 THEN NULL ELSE worker_id END, lease_until = CASE WHEN ? = 1 THEN NULL ELSE lease_until END, heartbeat_at = CASE WHEN ? = 1 THEN NULL ELSE heartbeat_at END WHERE task_id = ?",
                (status, now, version, int(retry), int(resume_input is not None), json.dumps(resume_input, ensure_ascii=False) if resume_input is not None else None, int(resume_input is not None), int(resume_input is not None), int(resume_input is not None), task_id),
            )
            conn.execute(
                "INSERT INTO human_review_action(task_id, action, comment, created_at) VALUES (?, ?, ?, ?)",
                (task_id, action, comment, now),
            )
            if checkpoint is not None:
                conn.execute(
                    "INSERT INTO agent_task_artifact(task_id, artifact_type, name, content_json, created_at, execution_version) VALUES (?, 'workflow_checkpoint', 'review', ?, ?, ?)",
                    (task_id, json.dumps(checkpoint, ensure_ascii=False), now, version),
                )

            next_seq = int(conn.execute(
                "SELECT COALESCE(MAX(event_seq), 0) + 1 FROM agent_task_event WHERE task_id = ?",
                (task_id,),
            ).fetchone()[0])
            for event in events:
                event_id = str(event.get("event_id") or f"evt_{uuid4().hex}")
                if conn.execute("SELECT 1 FROM agent_task_event WHERE event_id = ?", (event_id,)).fetchone():
                    continue
                conn.execute(
                    "INSERT INTO agent_task_event(event_id, task_id, event_type, node, agent, status, content, data_json, created_at, event_seq, execution_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id, task_id, event.get("type", "human_review"), event.get("node"),
                        event.get("agent", "human_reviewer"), event.get("status", status),
                        event.get("content"), json.dumps(event.get("data", {}), ensure_ascii=False),
                        event.get("timestamp") or now, next_seq, version,
                    ),
                )
                next_seq += 1

    def list_tasks(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT task_id, goal, project_path, status, created_at, updated_at, final_report, request_id, actor_id, role, idempotency_key, execution_version, retry_count, resume_count, worker_id, lease_until, heartbeat_at, attempt, error_code, error_message, failed_at
                FROM agent_task
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """
                , (max(1, min(limit, 1000)), max(0, offset))
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT task_id, goal, project_path, status, created_at, updated_at, final_report, request_id, actor_id, role, idempotency_key, execution_version, retry_count, resume_count, worker_id, lease_until, heartbeat_at, attempt, error_code, error_message, failed_at
                FROM agent_task
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_task_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_task WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        return dict(row) if row else None

    def get_task_input(self, task_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT input_json FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            return {}
        try:
            value = json.loads(row["input_json"] or "{}")
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def claim_next_task(self, worker_id: str, lease_seconds: int = 30) -> dict[str, Any] | None:
        """Atomically claim one queued or expired task for a local worker."""
        from datetime import datetime, timedelta

        now = utc_now_iso()
        lease_until = (datetime.now(BEIJING_TZ) + timedelta(seconds=max(1, lease_seconds))).strftime("%Y-%m-%d, %H:%M:%S")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM agent_task WHERE status = 'queued' OR (status = 'running' AND lease_until IS NOT NULL AND lease_until < ?) ORDER BY created_at LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE agent_task SET status = 'running', worker_id = ?, lease_until = ?, heartbeat_at = ?, attempt = attempt + 1, updated_at = ? WHERE task_id = ?",
                (worker_id, lease_until, now, now, row["task_id"]),
            )
            claimed = conn.execute("SELECT * FROM agent_task WHERE task_id = ?", (row["task_id"],)).fetchone()
        return dict(claimed) if claimed else None

    def claim_task(self, task_id: str, worker_id: str, lease_seconds: int = 30) -> dict[str, Any] | None:
        """Claim a specific queued task for a process-spawned worker."""
        from datetime import datetime, timedelta

        now = utc_now_iso()
        lease_until = (datetime.now(BEIJING_TZ) + timedelta(seconds=max(1, lease_seconds))).strftime("%Y-%m-%d, %H:%M:%S")
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE agent_task SET status = 'running', worker_id = ?, lease_until = ?, heartbeat_at = ?, attempt = attempt + 1, updated_at = ? WHERE task_id = ? AND status IN ('created', 'queued')",
                (worker_id, lease_until, now, now, task_id),
            )
            if result.rowcount != 1:
                return None
            row = conn.execute("SELECT * FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def heartbeat_task(self, task_id: str, worker_id: str, lease_seconds: int = 30) -> bool:
        from datetime import datetime, timedelta

        now = utc_now_iso()
        lease_until = (datetime.now(BEIJING_TZ) + timedelta(seconds=max(1, lease_seconds))).strftime("%Y-%m-%d, %H:%M:%S")
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE agent_task SET heartbeat_at = ?, lease_until = ?, updated_at = ? WHERE task_id = ? AND worker_id = ? AND status = 'running'",
                (now, lease_until, now, task_id, worker_id),
            )
        return result.rowcount == 1

    def register_worker(self, worker_id: str, pid: int) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_worker(worker_id, pid, started_at, last_heartbeat, status, active_task_id) VALUES (?, ?, ?, ?, 'running', NULL) ON CONFLICT(worker_id) DO UPDATE SET pid = excluded.pid, started_at = excluded.started_at, last_heartbeat = excluded.last_heartbeat, status = 'running', active_task_id = NULL",
                (worker_id, pid, now, now),
            )

    def heartbeat_worker(self, worker_id: str, active_task_id: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE agent_worker SET last_heartbeat = ?, status = 'running', active_task_id = ? WHERE worker_id = ?", (utc_now_iso(), active_task_id, worker_id))

    def unregister_worker(self, worker_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE agent_worker SET last_heartbeat = ?, status = 'stopped', active_task_id = NULL WHERE worker_id = ?", (utc_now_iso(), worker_id))

    def list_workers(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT worker_id, pid, started_at, last_heartbeat, status, active_task_id, restart_count FROM agent_worker ORDER BY started_at").fetchall()
        return [dict(row) for row in rows]

    def recover_expired_tasks(self) -> int:
        return len(self.recover_expired_task_ids())

    def recover_expired_task_ids(self) -> list[str]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT task_id, worker_id, execution_version FROM agent_task WHERE status = 'running' AND lease_until IS NOT NULL AND lease_until < ?",
                (now,),
            ).fetchall()
            for row in rows:
                task_id = str(row["task_id"])
                next_version = int(row["execution_version"]) + 1
                conn.execute(
                    "UPDATE agent_task SET status = 'queued', worker_id = NULL, lease_until = NULL, heartbeat_at = NULL, updated_at = ?, execution_version = ? WHERE task_id = ? AND status = 'running'",
                    (now, next_version, task_id),
                )
                sequence = conn.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM agent_task_event WHERE task_id = ?", (task_id,)).fetchone()[0]
                conn.execute(
                    "INSERT INTO agent_task_event(event_id, task_id, event_type, status, content, data_json, created_at, event_seq, execution_version) VALUES (?, ?, 'worker_recovered', 'queued', ?, ?, ?, ?, ?)",
                    (f"evt_recovered_{task_id}_{next_version}", task_id, f"Lease expired for worker {row['worker_id'] or 'unknown'}.", json.dumps({"worker_id": row["worker_id"]}, ensure_ascii=False), now, sequence, next_version),
                )
        return [str(row["task_id"]) for row in rows]

    def is_task_cancelled(self, task_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
        return bool(row and row["status"] == "cancelled")

    def is_task_failed(self, task_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM agent_task WHERE task_id = ?", (task_id,)).fetchone()
        return bool(row and row["status"] == "failed")

    def get_events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, task_id, event_type AS type, node, agent, status, content, data_json, created_at AS timestamp, event_seq
                FROM agent_task_event
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("data_json") or "{}")
            events.append(item)
        return events

    def get_events_after(self, task_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        return [event for event in self.get_events(task_id) if int(event.get("event_seq") or 0) > after_seq]

    def get_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT artifact_type, name, content_json, created_at
                FROM agent_task_artifact
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        artifacts = []
        for row in rows:
            item = dict(row)
            item["content"] = json.loads(item.pop("content_json") or "null")
            artifacts.append(item)
        return artifacts

    # 把工作流定义也纳入持久化，而不是只保存在前端 JSON 里
    def save_workflow(
        self,
        workflow_id: str,
        name: str,
        description: str | None,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM workflow_definition WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_definition(
                    workflow_id, name, description, nodes_json, edges_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    name,
                    description,
                    json.dumps(nodes, ensure_ascii=False),
                    json.dumps(edges, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )
        return self.get_workflow(workflow_id) or {}

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_id, name, description, nodes_json, edges_json, created_at, updated_at
                FROM workflow_definition
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._workflow_row_to_dict(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT workflow_id, name, description, nodes_json, edges_json, created_at, updated_at
                FROM workflow_definition
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return self._workflow_row_to_dict(row) if row else None

    def record_review_action(self, task_id: str, action: str, comment: str | None = None) -> dict[str, Any]:
        created_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO human_review_action(task_id, action, comment, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, action, comment, created_at),
            )
        return {"task_id": task_id, "action": action, "comment": comment, "created_at": created_at}

    def save_learning_plan(
        self,
        plan_id: str,
        task_id: str,
        topic: str,
        level: str,
        plan: list[dict[str, Any]],
        quiz: list[dict[str, Any]],
        report_markdown: str,
        status: str = "active",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO learning_plan(
                    plan_id, task_id, topic, level, status, plan_json, quiz_json,
                    report_markdown, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    task_id,
                    topic,
                    level,
                    status,
                    json.dumps(plan, ensure_ascii=False),
                    json.dumps(quiz, ensure_ascii=False),
                    report_markdown,
                    now,
                    now,
                ),
            )
        return self.get_learning_plan(plan_id) or {}

    def list_learning_plans(self, task_id: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT plan_id, task_id, topic, level, status, plan_json, quiz_json,
                   report_markdown, created_at, updated_at
            FROM learning_plan
        """
        params: tuple[Any, ...] = ()
        if task_id:
            query += " WHERE task_id = ?"
            params = (task_id,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._learning_plan_row_to_dict(row) for row in rows]

    def get_learning_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT plan_id, task_id, topic, level, status, plan_json, quiz_json,
                       report_markdown, created_at, updated_at
                FROM learning_plan
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
        return self._learning_plan_row_to_dict(row) if row else None

    def update_learning_plan_status(self, plan_id: str, status: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE learning_plan
                SET status = ?, updated_at = ?
                WHERE plan_id = ?
                """,
                (status, utc_now_iso(), plan_id),
            )
        return self.get_learning_plan(plan_id)

    def save_llm_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        record = {
            "trace_id": trace.get("trace_id"),
            "agent": trace.get("agent") or "unknown",
            "prompt_version": trace.get("prompt_version") or "v1",
            "model": trace.get("model"),
            "input": trace.get("input"),
            "output": trace.get("output"),
            "fallback_used": bool(trace.get("fallback_used")),
            "error_message": trace.get("error_message"),
            "latency_ms": int(trace.get("latency_ms") or 0),
            "token_usage": trace.get("token_usage") or {},
            "request_id": trace.get("request_id"),
            "actor_id": trace.get("actor_id"),
            "role": trace.get("role"),
            "created_at": trace.get("created_at") or utc_now_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_call_trace(
                    trace_id, agent, prompt_version, model, input_json, output_text,
                    fallback_used, error_message, latency_ms, token_usage_json, request_id, actor_id, role, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["trace_id"],
                    record["agent"],
                    record["prompt_version"],
                    record["model"],
                    json.dumps(record["input"], ensure_ascii=False),
                    record["output"],
                    1 if record["fallback_used"] else 0,
                    record["error_message"],
                    record["latency_ms"],
                    json.dumps(record["token_usage"], ensure_ascii=False),
                    record["request_id"], record["actor_id"], record["role"],
                    record["created_at"],
                ),
            )
        return record

    def list_llm_traces(self, limit: int = 50, agent: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        query = """
            SELECT trace_id, agent, prompt_version, model, input_json, output_text,
                   fallback_used, error_message, latency_ms, token_usage_json, request_id, actor_id, role, created_at
            FROM llm_call_trace
        """
        params: list[Any] = []
        if agent:
            query += " WHERE agent = ?"
            params.append(agent)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        traces: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["input"] = json.loads(item.pop("input_json") or "{}")
            item["token_usage"] = json.loads(item.pop("token_usage_json") or "{}")
            item["fallback_used"] = bool(item["fallback_used"])
            traces.append(item)
        return traces

    def upsert_prompt_version(self, prompt: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        agent = str(prompt.get("agent") or "unknown")
        prompt_version = str(prompt.get("prompt_version") or "v1")
        prompt_family = str(prompt.get("prompt_family") or self._prompt_family(prompt_version))
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT created_at FROM llm_prompt_version
                WHERE agent = ? AND prompt_version = ?
                """,
                (agent, prompt_version),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_prompt_version(
                    agent, prompt_family, prompt_version, title, description, system_suffix,
                    is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent,
                    prompt_family,
                    prompt_version,
                    str(prompt.get("title") or prompt_version),
                    prompt.get("description"),
                    prompt.get("system_suffix"),
                    1 if prompt.get("is_active") else 0,
                    created_at,
                    now,
                ),
            )
        return self.get_prompt_version(agent, prompt_version) or {}

    def set_active_prompt_version(self, agent: str, prompt_version: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT agent, prompt_family, prompt_version FROM llm_prompt_version
                WHERE agent = ? AND prompt_version = ?
                """,
                (agent, prompt_version),
            ).fetchone()
            if not row:
                return None
            prompt_family = row["prompt_family"] or self._prompt_family(prompt_version)
            conn.execute(
                """
                UPDATE llm_prompt_version
                SET is_active = 0, updated_at = ?
                WHERE agent = ? AND prompt_family = ?
                """,
                (now, agent, prompt_family),
            )
            conn.execute(
                """
                UPDATE llm_prompt_version
                SET is_active = 1, updated_at = ?
                WHERE agent = ? AND prompt_version = ?
                """,
                (now, agent, prompt_version),
            )
        return self.get_prompt_version(agent, prompt_version)

    def get_prompt_version(self, agent: str, prompt_version: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT agent, prompt_version, title, description, system_suffix,
                       prompt_family, is_active, created_at, updated_at
                FROM llm_prompt_version
                WHERE agent = ? AND prompt_version = ?
                """,
                (agent, prompt_version),
            ).fetchone()
        return self._prompt_row_to_dict(row) if row else None

    def list_prompt_versions(self, agent: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT agent, prompt_version, title, description, system_suffix,
                   prompt_family, is_active, created_at, updated_at
            FROM llm_prompt_version
        """
        params: list[Any] = []
        if agent:
            query += " WHERE agent = ?"
            params.append(agent)
        query += " ORDER BY agent ASC, prompt_version ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._prompt_row_to_dict(row) for row in rows]

    def get_active_prompt_version(self, agent: str, prompt_family: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT agent, prompt_version, title, description, system_suffix,
                       prompt_family, is_active, created_at, updated_at
                FROM llm_prompt_version
                WHERE agent = ? AND prompt_family = ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (agent, prompt_family),
            ).fetchone()
        return self._prompt_row_to_dict(row) if row else None

    def llm_usage_summary(self, limit: int = 500, agent: str | None = None) -> dict[str, Any]:
        traces = self.list_llm_traces(limit=limit, agent=agent)
        by_agent: dict[str, dict[str, Any]] = {}
        by_model: dict[str, dict[str, Any]] = {}
        by_prompt: dict[str, dict[str, Any]] = {}
        total = self._usage_bucket("all")
        for trace in traces:
            usage = trace.get("token_usage") if isinstance(trace.get("token_usage"), dict) else {}
            input_tokens, output_tokens, total_tokens = self._token_counts(usage)
            fallback_used = bool(trace.get("fallback_used"))
            latency_ms = int(trace.get("latency_ms") or 0)
            agent_name = str(trace.get("agent") or "unknown")
            model = str(trace.get("model") or "fallback")
            prompt_version = str(trace.get("prompt_version") or "v1")
            prompt_key = f"{agent_name}:{prompt_version}"
            self._add_usage(total, input_tokens, output_tokens, total_tokens, latency_ms, fallback_used)
            self._add_usage(by_agent.setdefault(agent_name, self._usage_bucket(agent_name)), input_tokens, output_tokens, total_tokens, latency_ms, fallback_used)
            self._add_usage(by_model.setdefault(model, self._usage_bucket(model)), input_tokens, output_tokens, total_tokens, latency_ms, fallback_used)
            self._add_usage(by_prompt.setdefault(prompt_key, self._usage_bucket(prompt_key)), input_tokens, output_tokens, total_tokens, latency_ms, fallback_used)
        return {
            "total": self._finalize_usage(total),
            "by_agent": [self._finalize_usage(item) for item in by_agent.values()],
            "by_model": [self._finalize_usage(item) for item in by_model.values()],
            "by_prompt": [self._finalize_usage(item) for item in by_prompt.values()],
            "sample_size": len(traces),
        }

    def seed_builtin_skills(self, plugin: dict[str, Any], skills: list[dict[str, Any]]) -> None:
        from app.skills.contract import validate_skill_contract

        now = utc_now_iso()
        with self._connect() as conn:
            existing_plugin = conn.execute(
                "SELECT installed_at FROM skill_plugin WHERE plugin_id = ?",
                (plugin["plugin_id"],),
            ).fetchone()
            installed_at = existing_plugin["installed_at"] if existing_plugin else now
            conn.execute(
                """
                INSERT OR REPLACE INTO skill_plugin(
                    plugin_id, name, version, source_type, source_url, author,
                    description, enabled, installed_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plugin["plugin_id"],
                    plugin["name"],
                    plugin.get("version") or "1.0.0",
                    plugin.get("source_type") or "builtin",
                    plugin.get("source_url"),
                    plugin.get("author"),
                    plugin.get("description"),
                    1 if plugin.get("enabled", True) else 0,
                    installed_at,
                    now,
                ),
            )
            for skill in skills:
                contract = skill.get("contract") if isinstance(skill.get("contract"), dict) else validate_skill_contract(skill)
                skill = {
                    **skill,
                    "permission_levels": skill.get("permission_levels") or contract.get("permission_levels") or [],
                    "risk_level": skill.get("risk_level") or contract.get("risk_level") or "low",
                    "contract": contract,
                }
                existing_skill = conn.execute(
                    "SELECT created_at, enabled FROM skill_registry WHERE skill_code = ?",
                    (skill["code"],),
                ).fetchone()
                created_at = existing_skill["created_at"] if existing_skill else now
                enabled = existing_skill["enabled"] if existing_skill else 1
                conn.execute(
                    """
                    INSERT OR REPLACE INTO skill_registry(
                        skill_code, plugin_id, name, description, category, execution_type,
                        permissions_json, permission_levels_json, risk_level, input_schema_json,
                        output_schema_json, default_input_json, dependencies_json, tests_json,
                        version, entrypoint, source_format, contract_json, enabled, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        skill["code"],
                        skill.get("source_plugin") or plugin["plugin_id"],
                        skill["name"],
                        skill.get("description"),
                        skill.get("category") or "general",
                        skill.get("execution_type") or "agent",
                        json.dumps(skill.get("permissions") or [], ensure_ascii=False),
                        json.dumps(skill.get("permission_levels") or [], ensure_ascii=False),
                        skill.get("risk_level") or "low",
                        json.dumps(skill.get("input_schema") or {}, ensure_ascii=False),
                        json.dumps(skill.get("output_schema") or {}, ensure_ascii=False),
                        json.dumps(skill.get("default_input") or {}, ensure_ascii=False),
                        json.dumps(skill.get("dependencies") or [], ensure_ascii=False),
                        json.dumps(skill.get("tests") or [], ensure_ascii=False),
                        skill.get("version") or plugin.get("version") or "1.0.0",
                        skill.get("entrypoint"),
                        skill.get("source_format") or "plugin_json",
                        json.dumps(skill.get("contract") or {}, ensure_ascii=False),
                        enabled,
                        created_at,
                        now,
                    ),
                )
                if not conn.execute(
                    "SELECT id FROM skill_approval WHERE skill_code = ? AND agent_code = ?",
                    (skill["code"], "skill_console"),
                ).fetchone():
                    conn.execute(
                        """
                        INSERT INTO skill_approval(skill_code, agent_code, allowed, reason, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (skill["code"], "skill_console", 1, "Installed skill approved for console testing.", now, now),
                    )
                snapshot = {
                    **skill,
                    "source_plugin": skill.get("source_plugin") or plugin["plugin_id"],
                    "version": skill.get("version") or plugin.get("version") or "1.0.0",
                }
                conn.execute(
                    """
                    INSERT OR REPLACE INTO skill_version_snapshot(
                        skill_code, plugin_id, version, snapshot_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        skill["code"],
                        snapshot["source_plugin"],
                        snapshot["version"],
                        json.dumps(snapshot, ensure_ascii=False),
                        now,
                    ),
                )

    def list_skill_plugins(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT plugin_id, name, version, source_type, source_url, author,
                       description, enabled, installed_at, updated_at
                FROM skill_plugin
                ORDER BY installed_at DESC
                """
            ).fetchall()
        return [self._skill_plugin_row_to_dict(row) for row in rows]

    def list_skills(self, category: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT skill_code, plugin_id, name, description, category, execution_type,
                   permissions_json, permission_levels_json, risk_level, input_schema_json,
                   output_schema_json, default_input_json, dependencies_json, tests_json,
                   version, entrypoint, source_format, contract_json, enabled, created_at, updated_at
            FROM skill_registry
        """
        params: list[Any] = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY category ASC, skill_code ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._skill_row_to_dict(row) for row in rows]

    def get_skill(self, skill_code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT skill_code, plugin_id, name, description, category, execution_type,
                       permissions_json, permission_levels_json, risk_level, input_schema_json,
                       output_schema_json, default_input_json, dependencies_json, tests_json,
                       version, entrypoint, source_format, contract_json, enabled, created_at, updated_at
                FROM skill_registry
                WHERE skill_code = ?
                """,
                (skill_code,),
            ).fetchone()
        return self._skill_row_to_dict(row) if row else None

    def update_skill_enabled(self, skill_code: str, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE skill_registry SET enabled = ?, updated_at = ? WHERE skill_code = ?",
                (1 if enabled else 0, utc_now_iso(), skill_code),
            )
        return self.get_skill(skill_code)

    def uninstall_skill_plugin(self, plugin_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            plugin = conn.execute(
                """
                SELECT plugin_id, name, version, source_type, source_url, author,
                       description, enabled, installed_at, updated_at
                FROM skill_plugin
                WHERE plugin_id = ?
                """,
                (plugin_id,),
            ).fetchone()
            if not plugin:
                return None
            plugin_item = self._skill_plugin_row_to_dict(plugin)
            if plugin_item["source_type"] == "builtin":
                raise ValueError("Built-in skill plugins cannot be uninstalled.")
            skill_rows = conn.execute(
                "SELECT skill_code FROM skill_registry WHERE plugin_id = ?",
                (plugin_id,),
            ).fetchall()
            skill_codes = [row["skill_code"] for row in skill_rows]
            for skill_code in skill_codes:
                conn.execute("DELETE FROM skill_approval WHERE skill_code = ?", (skill_code,))
            conn.execute("DELETE FROM skill_registry WHERE plugin_id = ?", (plugin_id,))
            conn.execute("DELETE FROM skill_plugin WHERE plugin_id = ?", (plugin_id,))
        return {
            "plugin": plugin_item,
            "removed_skills": skill_codes,
            "removed_skill_count": len(skill_codes),
        }

    def set_skill_approval(self, skill_code: str, agent_code: str, allowed: bool, reason: str | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM skill_approval WHERE skill_code = ? AND agent_code = ?",
                (skill_code, agent_code),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO skill_approval(
                    skill_code, agent_code, allowed, reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (skill_code, agent_code, 1 if allowed else 0, reason, created_at, now),
            )
        return self.get_skill_approval(skill_code, agent_code) or {}

    def get_skill_approval(self, skill_code: str, agent_code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT skill_code, agent_code, allowed, reason, created_at, updated_at
                FROM skill_approval
                WHERE skill_code = ? AND agent_code = ?
                """,
                (skill_code, agent_code),
            ).fetchone()
        return self._skill_approval_row_to_dict(row) if row else None

    def list_skill_approvals(self, agent_code: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT skill_code, agent_code, allowed, reason, created_at, updated_at
            FROM skill_approval
        """
        params: list[Any] = []
        if agent_code:
            query += " WHERE agent_code = ?"
            params.append(agent_code)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._skill_approval_row_to_dict(row) for row in rows]

    def save_skill_execution_log(self, log: dict[str, Any]) -> dict[str, Any]:
        created_at = log.get("created_at") or utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO skill_execution_log(
                    log_id, skill_code, agent_code, task_id, input_json, output_json,
                    status, error_message, latency_ms, request_id, actor_id, role, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log["log_id"],
                    log["skill_code"],
                    log.get("agent_code"),
                    log.get("task_id"),
                    json.dumps(log.get("input") or {}, ensure_ascii=False),
                    json.dumps(log.get("output") or {}, ensure_ascii=False),
                    log.get("status") or "completed",
                    log.get("error_message"),
                    int(log.get("latency_ms") or 0),
                    log.get("request_id"), log.get("actor_id"), log.get("role"),
                    created_at,
                ),
            )
        return {
            **log,
            "created_at": created_at,
            "input": log.get("input") or {},
            "output": log.get("output") or {},
            "latency_ms": int(log.get("latency_ms") or 0),
        }

    def list_skill_execution_logs(self, limit: int = 100, skill_code: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT log_id, skill_code, agent_code, task_id, input_json, output_json,
                   status, error_message, latency_ms, request_id, actor_id, role, created_at
            FROM skill_execution_log
        """
        params: list[Any] = []
        if skill_code:
            query += " WHERE skill_code = ?"
            params.append(skill_code)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._skill_log_row_to_dict(row) for row in rows]

    def list_skill_versions(self, skill_code: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT skill_code, plugin_id, version, snapshot_json, created_at
                FROM skill_version_snapshot
                WHERE skill_code = ?
                ORDER BY id DESC
                """,
                (skill_code,),
            ).fetchall()
        versions = []
        for row in rows:
            item = dict(row)
            item["snapshot"] = json.loads(item.pop("snapshot_json") or "{}")
            versions.append(item)
        return versions

    def rollback_skill_version(self, skill_code: str, version: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT snapshot_json
                FROM skill_version_snapshot
                WHERE skill_code = ? AND version = ?
                """,
                (skill_code, version),
            ).fetchone()
        if not row:
            return None
        snapshot = json.loads(row["snapshot_json"] or "{}")
        plugin = {
            "plugin_id": snapshot.get("source_plugin") or snapshot.get("plugin_id") or "rollback",
            "name": snapshot.get("source_plugin") or snapshot.get("plugin_id") or "Rollback Plugin",
            "version": version,
            "source_type": "rollback",
            "enabled": True,
        }
        self.seed_builtin_skills(plugin, [{**snapshot, "version": version}])
        return self.get_skill(skill_code)

    def save_marketplace_install(self, record: dict[str, Any]) -> dict[str, Any]:
        installed_at = record.get("installed_at") or utc_now_iso()
        summary = record.get("summary") or {}
        manifest = record.get("manifest") or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plugin_marketplace_install(
                    install_id, package_id, name, package_type, version, source_url,
                    status, summary_json, manifest_json, error_message, approval_status,
                    approved_by, approved_at, approval_reason, installed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["install_id"],
                    record["package_id"],
                    record["name"],
                    record["package_type"],
                    record.get("version"),
                    record.get("source_url"),
                    record.get("status") or "installed",
                    json.dumps(summary, ensure_ascii=False),
                    json.dumps(manifest, ensure_ascii=False),
                    record.get("error_message"),
                    record.get("approval_status") or "approved",
                    record.get("approved_by"),
                    record.get("approved_at"),
                    record.get("approval_reason"),
                    installed_at,
                ),
            )
        return {**record, "summary": summary, "manifest": manifest, "installed_at": installed_at}

    def list_marketplace_installs(self, limit: int = 80, package_type: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT install_id, package_id, name, package_type, version, source_url,
                   status, summary_json, manifest_json, error_message, approval_status,
                   approved_by, approved_at, approval_reason, installed_at
            FROM plugin_marketplace_install
        """
        params: list[Any] = []
        if package_type:
            query += " WHERE package_type = ?"
            params.append(package_type)
        query += " ORDER BY installed_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._marketplace_install_row_to_dict(row) for row in rows]

    def get_latest_marketplace_install(self, package_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT install_id, package_id, name, package_type, version, source_url,
                       status, summary_json, manifest_json, error_message, approval_status,
                       approved_by, approved_at, approval_reason, installed_at
                FROM plugin_marketplace_install
                WHERE package_id = ?
                ORDER BY installed_at DESC, rowid DESC
                LIMIT 1
                """,
                (package_id,),
            ).fetchone()
        return self._marketplace_install_row_to_dict(row) if row else None

    def set_marketplace_approval(
        self, package_id: str, status: str, approved_by: str, reason: str | None = None
    ) -> dict[str, Any] | None:
        if status not in {"approved", "rejected"}:
            raise ValueError("approval status must be approved or rejected")
        latest = self.get_latest_marketplace_install(package_id)
        if not latest:
            return None
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE plugin_marketplace_install
                SET approval_status = ?, approved_by = ?, approved_at = ?, approval_reason = ?
                WHERE install_id = ?
                """,
                (status, approved_by, now, reason, latest["install_id"]),
            )
        return self.get_latest_marketplace_install(package_id)

    def _skill_plugin_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    def _skill_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["code"] = item.pop("skill_code")
        item["source_plugin"] = item["plugin_id"]
        item["permissions"] = json.loads(item.pop("permissions_json") or "[]")
        item["permission_levels"] = json.loads(item.pop("permission_levels_json") or "[]")
        item["input_schema"] = json.loads(item.pop("input_schema_json") or "{}")
        item["output_schema"] = json.loads(item.pop("output_schema_json") or "{}")
        item["default_input"] = json.loads(item.pop("default_input_json") or "{}")
        item["dependencies"] = json.loads(item.pop("dependencies_json") or "[]")
        item["tests"] = json.loads(item.pop("tests_json") or "[]")
        item["contract"] = json.loads(item.pop("contract_json") or "{}")
        item["enabled"] = bool(item["enabled"])
        return item

    def _skill_approval_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["allowed"] = bool(item["allowed"])
        return item

    def _skill_log_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json") or "{}")
        item["output"] = json.loads(item.pop("output_json") or "{}")
        return item

    def _marketplace_install_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json") or "{}")
        item["manifest"] = json.loads(item.pop("manifest_json") or "{}")
        return item

    def _workflow_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["nodes"] = json.loads(item.pop("nodes_json") or "[]")
        item["edges"] = json.loads(item.pop("edges_json") or "[]")
        return item

    def _learning_plan_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["plan"] = json.loads(item.pop("plan_json") or "[]")
        item["quiz"] = json.loads(item.pop("quiz_json") or "[]")
        return item

    def _prompt_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["is_active"] = bool(item["is_active"])
        return item

    def _prompt_family(self, prompt_version: str) -> str:
        parts = prompt_version.split(".")
        if len(parts) > 1 and parts[-1].startswith("v") and parts[-1][1:].isdigit():
            return ".".join(parts[:-1])
        return prompt_version

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # `save_mcp_server() / upsert_mcp_tool() / set_mcp_tool_approval() / save_mcp_call_log()`
    # 这组方法说明 MCP 不是临时调用，而是有完整治理链路的：注册 发现 启用/禁用 审批 调用日志
    def save_mcp_server(self, server: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        server_id = str(server.get("server_id") or server.get("name") or "").strip()
        if not server_id:
            raise ValueError("server_id is required")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM mcp_server_config WHERE server_id = ?",
                (server_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO mcp_server_config(
                    server_id, name, transport, command, args_json, env_json, url,
                    enabled, status, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    server_id,
                    str(server.get("name") or server_id),
                    str(server.get("transport") or "stdio"),
                    server.get("command"),
                    json.dumps(server.get("args") or [], ensure_ascii=False),
                    json.dumps(server.get("env") or {}, ensure_ascii=False),
                    server.get("url"),
                    1 if server.get("enabled") else 0,
                    str(server.get("status") or "unknown"),
                    server.get("last_error"),
                    created_at,
                    now,
                ),
            )
        return self.get_mcp_server(server_id) or {}

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT server_id, name, transport, command, args_json, env_json, url,
                       enabled, status, last_error, created_at, updated_at
                FROM mcp_server_config
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._mcp_server_row_to_dict(row) for row in rows]

    def get_mcp_server(self, server_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT server_id, name, transport, command, args_json, env_json, url,
                       enabled, status, last_error, created_at, updated_at
                FROM mcp_server_config
                WHERE server_id = ?
                """,
                (server_id,),
            ).fetchone()
        return self._mcp_server_row_to_dict(row) if row else None

    def update_mcp_server_status(self, server_id: str, status: str, last_error: str | None = None, enabled: bool | None = None) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as conn:
            if enabled is None:
                conn.execute(
                    "UPDATE mcp_server_config SET status = ?, last_error = ?, updated_at = ? WHERE server_id = ?",
                    (status, last_error, now, server_id),
                )
            else:
                conn.execute(
                    "UPDATE mcp_server_config SET status = ?, last_error = ?, enabled = ?, updated_at = ? WHERE server_id = ?",
                    (status, last_error, 1 if enabled else 0, now, server_id),
                )
        return self.get_mcp_server(server_id)

    def upsert_mcp_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        server_id = str(tool.get("server_id") or "").strip()
        name = str(tool.get("name") or "").strip()
        if not server_id or not name:
            raise ValueError("server_id and tool name are required")
        tool_id = str(tool.get("tool_id") or f"{server_id}:{name}")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT discovered_at FROM mcp_tool_registry WHERE server_id = ? AND name = ?",
                (server_id, name),
            ).fetchone()
            discovered_at = existing["discovered_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO mcp_tool_registry(
                    tool_id, server_id, name, description, input_schema_json,
                    enabled, status, discovered_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool_id,
                    server_id,
                    name,
                    tool.get("description"),
                    json.dumps(tool.get("input_schema") or {}, ensure_ascii=False),
                    1 if tool.get("enabled", True) else 0,
                    str(tool.get("status") or "available"),
                    discovered_at,
                    now,
                ),
            )
        return self.get_mcp_tool(server_id, name) or {}

    def prune_mcp_tools(self, server_id: str, keep_names: set[str]) -> int:
        names = {str(name).strip() for name in keep_names if str(name).strip()}
        if not server_id:
            return 0
        with self._connect() as conn:
            if not names:
                cursor = conn.execute("DELETE FROM mcp_tool_registry WHERE server_id = ?", (server_id,))
                return cursor.rowcount
            placeholders = ",".join("?" for _ in names)
            cursor = conn.execute(
                f"DELETE FROM mcp_tool_registry WHERE server_id = ? AND name NOT IN ({placeholders})",
                (server_id, *sorted(names)),
            )
            return cursor.rowcount

    def list_mcp_tools(self, server_id: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT tool_id, server_id, name, description, input_schema_json,
                   enabled, status, discovered_at, updated_at
            FROM mcp_tool_registry
        """
        params: list[Any] = []
        if server_id:
            query += " WHERE server_id = ?"
            params.append(server_id)
        query += " ORDER BY server_id ASC, name ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._mcp_tool_row_to_dict(row) for row in rows]

    def get_mcp_tool(self, server_id: str, name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT tool_id, server_id, name, description, input_schema_json,
                       enabled, status, discovered_at, updated_at
                FROM mcp_tool_registry
                WHERE server_id = ? AND name = ?
                """,
                (server_id, name),
            ).fetchone()
        return self._mcp_tool_row_to_dict(row) if row else None

    def update_mcp_tool_enabled(self, server_id: str, name: str, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE mcp_tool_registry SET enabled = ?, updated_at = ? WHERE server_id = ? AND name = ?",
                (1 if enabled else 0, utc_now_iso(), server_id, name),
            )
        return self.get_mcp_tool(server_id, name)

    def set_mcp_tool_approval(self, agent_code: str, server_id: str, tool_name: str, allowed: bool, reason: str | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT created_at FROM mcp_tool_approval
                WHERE agent_code = ? AND server_id = ? AND tool_name = ?
                """,
                (agent_code, server_id, tool_name),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO mcp_tool_approval(
                    agent_code, server_id, tool_name, allowed, reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (agent_code, server_id, tool_name, 1 if allowed else 0, reason, created_at, now),
            )
        return {"agent_code": agent_code, "server_id": server_id, "tool_name": tool_name, "allowed": allowed, "reason": reason, "created_at": created_at, "updated_at": now}

    def get_mcp_tool_approval(self, agent_code: str, server_id: str, tool_name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT agent_code, server_id, tool_name, allowed, reason, created_at, updated_at
                FROM mcp_tool_approval
                WHERE agent_code = ? AND server_id = ? AND tool_name = ?
                """,
                (agent_code, server_id, tool_name),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["allowed"] = bool(item["allowed"])
        return item

    def save_mcp_call_log(self, log: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mcp_tool_call_log(
                    call_id, server_id, tool_name, agent_code, input_json, output_json,
                    status, error_message, latency_ms, request_id, actor_id, role,
                    command_summary, exit_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log["call_id"],
                    log.get("server_id"),
                    log["tool_name"],
                    log.get("agent_code"),
                    json.dumps(log.get("input") or {}, ensure_ascii=False),
                    json.dumps(log.get("output") or {}, ensure_ascii=False),
                    log.get("status") or "unknown",
                    log.get("error_message"),
                    int(log.get("latency_ms") or 0),
                    log.get("request_id") or "",
                    log.get("actor_id") or "unknown",
                    log.get("role") or "unknown",
                    log.get("command_summary") or "",
                    log.get("exit_code"),
                    log.get("created_at") or utc_now_iso(),
                ),
            )
        return log

    def list_mcp_call_logs(self, limit: int = 100, server_id: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT rowid AS sort_id, call_id, server_id, tool_name, agent_code, input_json, output_json,
                   status, error_message, latency_ms, request_id, actor_id, role,
                   command_summary, exit_code, created_at
            FROM mcp_tool_call_log
        """
        params: list[Any] = []
        if server_id:
            query += " WHERE server_id = ?"
            params.append(server_id)
        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        logs = []
        for row in rows:
            item = dict(row)
            item.pop("sort_id", None)
            item["input"] = json.loads(item.pop("input_json") or "{}")
            item["output"] = json.loads(item.pop("output_json") or "{}")
            logs.append(item)
        return logs

    def create_benchmark_run(
        self,
        run_id: str,
        name: str,
        benchmark_type: str,
        config: dict[str, Any],
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO benchmark_run(
                    run_id, name, benchmark_type, status, config_json, summary_json,
                    started_at, finished_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    name,
                    benchmark_type,
                    "running",
                    json.dumps(config, ensure_ascii=False),
                    json.dumps(summary or {}, ensure_ascii=False),
                    now,
                    None,
                    now,
                ),
            )
        return self.get_benchmark_run(run_id) or {}

    def append_benchmark_result(self, result: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO benchmark_result(
                    run_id, case_id, server_id, tool_name, iteration, status, latency_ms,
                    error_message, input_json, output_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["run_id"],
                    result["case_id"],
                    result.get("server_id"),
                    result.get("tool_name"),
                    int(result.get("iteration") or 1),
                    result.get("status") or "unknown",
                    int(result.get("latency_ms") or 0),
                    result.get("error_message"),
                    json.dumps(result.get("input") or {}, ensure_ascii=False),
                    json.dumps(result.get("output") or {}, ensure_ascii=False),
                    result.get("created_at") or utc_now_iso(),
                ),
            )
            result["id"] = cursor.lastrowid
        return result

    def finish_benchmark_run(self, run_id: str, status: str, summary: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE benchmark_run
                SET status = ?, summary_json = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (status, json.dumps(summary, ensure_ascii=False), utc_now_iso(), run_id),
            )
        return self.get_benchmark_run(run_id) or {}

    def list_benchmark_runs(self, limit: int = 50, benchmark_type: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT rowid AS sort_id, run_id, name, benchmark_type, status, config_json,
                   summary_json, started_at, finished_at, created_at
            FROM benchmark_run
        """
        params: list[Any] = []
        if benchmark_type:
            query += " WHERE benchmark_type = ?"
            params.append(benchmark_type)
        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._benchmark_run_row_to_dict(row) for row in rows]

    def get_benchmark_run(self, run_id: str, *, include_results: bool = True) -> dict[str, Any] | None:
        with self._connect() as conn:
            run_row = conn.execute(
                """
                SELECT rowid AS sort_id, run_id, name, benchmark_type, status, config_json,
                       summary_json, started_at, finished_at, created_at
                FROM benchmark_run
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if not run_row:
                return None
            run = self._benchmark_run_row_to_dict(run_row)
            if include_results:
                rows = conn.execute(
                    """
                    SELECT id, run_id, case_id, server_id, tool_name, iteration, status,
                           latency_ms, error_message, input_json, output_json, created_at
                    FROM benchmark_result
                    WHERE run_id = ?
                    ORDER BY id ASC
                    """,
                    (run_id,),
                ).fetchall()
                run["results"] = [self._benchmark_result_row_to_dict(row) for row in rows]
        return run

    def _mcp_server_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["args"] = json.loads(item.pop("args_json") or "[]")
        item["env"] = json.loads(item.pop("env_json") or "{}")
        item["enabled"] = bool(item["enabled"])
        return item

    def _mcp_tool_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["input_schema"] = json.loads(item.pop("input_schema_json") or "{}")
        item["enabled"] = bool(item["enabled"])
        return item

    def _benchmark_run_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item.pop("sort_id", None)
        item["config"] = json.loads(item.pop("config_json") or "{}")
        item["summary"] = json.loads(item.pop("summary_json") or "{}")
        item.setdefault("results", [])
        return item

    def _benchmark_result_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json") or "{}")
        item["output"] = json.loads(item.pop("output_json") or "{}")
        return item

    def _usage_bucket(self, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "calls": 0,
            "fallback_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
        }

    def _add_usage(
        self,
        bucket: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        latency_ms: int,
        fallback_used: bool,
    ) -> None:
        bucket["calls"] += 1
        bucket["fallback_calls"] += 1 if fallback_used else 0
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["total_tokens"] += total_tokens
        bucket["latency_ms"] += latency_ms

    def _finalize_usage(self, bucket: dict[str, Any]) -> dict[str, Any]:
        calls = int(bucket["calls"] or 0)
        return {
            **bucket,
            "avg_latency_ms": int(bucket["latency_ms"] / calls) if calls else 0,
            "fallback_rate": round(float(bucket["fallback_calls"]) / calls, 4) if calls else 0,
        }

    def _token_counts(self, usage: dict[str, Any]) -> tuple[int, int, int]:
        input_tokens = int(
            usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or usage.get("input_token_count")
            or 0
        )
        output_tokens = int(
            usage.get("output_tokens")
            or usage.get("completion_tokens")
            or usage.get("output_token_count")
            or 0
        )
        total_tokens = int(usage.get("total_tokens") or usage.get("total_token_count") or input_tokens + output_tokens)
        return input_tokens, output_tokens, total_tokens


task_store = SQLiteTaskStore()
