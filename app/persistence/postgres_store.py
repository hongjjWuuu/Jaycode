"""PostgreSQL persistence adapter and idempotent schema contract.

The adapter is opt-in through ``DATABASE_URL`` and never migrates SQLite data.
The generic tables cover the persistence domains so each domain can be wired to
the same backend contract without making SQLite data migration implicit.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from app.harness.events import utc_now_iso


class PostgresTaskStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL store")
        self.database_url = database_url

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - dependency is optional at runtime
            raise RuntimeError("psycopg is required for PostgreSQL store") from exc
        with psycopg.connect(self.database_url) as conn:
            yield conn

    def init_schema(self) -> None:
        statements = (
            "CREATE TABLE IF NOT EXISTS jaycode_schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())",
            """
            CREATE TABLE IF NOT EXISTS agent_task (
                task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, project_path TEXT,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                final_report TEXT, request_id TEXT, actor_id TEXT, role TEXT,
                idempotency_key TEXT UNIQUE, input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                execution_version INTEGER NOT NULL DEFAULT 1, retry_count INTEGER NOT NULL DEFAULT 0,
                resume_count INTEGER NOT NULL DEFAULT 0, worker_id TEXT, lease_until TEXT,
                heartbeat_at TEXT, attempt INTEGER NOT NULL DEFAULT 0,
                error_code TEXT, error_message TEXT, failed_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_task_event (
                event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES agent_task(task_id) ON DELETE CASCADE,
                event_type TEXT NOT NULL, node TEXT, agent TEXT, status TEXT, content TEXT,
                data_json JSONB NOT NULL DEFAULT '{}'::jsonb, event_seq INTEGER NOT NULL,
                execution_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                UNIQUE(task_id, event_seq)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_task_artifact (
                id BIGSERIAL PRIMARY KEY, task_id TEXT NOT NULL REFERENCES agent_task(task_id) ON DELETE CASCADE,
                artifact_type TEXT NOT NULL, name TEXT NOT NULL, content_json JSONB,
                execution_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS security_audit_log (
                audit_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                role TEXT NOT NULL, action TEXT NOT NULL, resource_type TEXT NOT NULL,
                resource_id TEXT, status TEXT NOT NULL, metadata_json JSONB, created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_pg_task_queue ON agent_task(status, lease_until, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_event_task_created ON agent_task_event(task_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_audit_action_created ON security_audit_log(action, created_at)",
        )
        with self.connection() as conn, conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute("INSERT INTO jaycode_schema_version(version) VALUES (1) ON CONFLICT(version) DO NOTHING")

    def init_full_schema(self) -> None:
        """Create the remaining persistence-domain tables idempotently.

        Domain services may adopt these tables incrementally.  JSONB keeps the
        contract compatible with the existing SQLite JSON payloads while the
        relational identifiers and timestamps remain queryable and indexed.
        """
        self.init_schema()
        statements = (
            "CREATE EXTENSION IF NOT EXISTS vector",
            """CREATE TABLE IF NOT EXISTS workflow_definition (
                workflow_id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 1,
                definition_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS human_review_action (
                review_id TEXT PRIMARY KEY, task_id TEXT REFERENCES agent_task(task_id),
                actor_id TEXT NOT NULL, action TEXT NOT NULL, payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS skill_registry (
                skill_id TEXT PRIMARY KEY, version TEXT NOT NULL, manifest_json JSONB NOT NULL,
                approval_status TEXT NOT NULL DEFAULT 'pending', updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(skill_id, version)
            )""",
            """CREATE TABLE IF NOT EXISTS skill_execution_log (
                log_id TEXT PRIMARY KEY, skill_code TEXT NOT NULL, task_id TEXT,
                request_id TEXT, actor_id TEXT, role TEXT, status TEXT NOT NULL,
                latency_ms INTEGER NOT NULL DEFAULT 0, error_message TEXT,
                input_json JSONB, output_json JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS skill_approval (
                skill_code TEXT NOT NULL, agent_code TEXT NOT NULL, allowed BOOLEAN NOT NULL,
                reason TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(skill_code, agent_code)
            )""",
            """CREATE TABLE IF NOT EXISTS mcp_server_config (
                server_id TEXT PRIMARY KEY, command TEXT NOT NULL, args_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                env_json JSONB NOT NULL DEFAULT '{}'::jsonb, enabled BOOLEAN NOT NULL DEFAULT false,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS mcp_tool_call_log (
                call_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, actor_id TEXT NOT NULL, role TEXT NOT NULL,
                server_id TEXT NOT NULL, tool_name TEXT NOT NULL, status TEXT NOT NULL, exit_code INTEGER,
                latency_ms INTEGER, error_message TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS mcp_tool_registry (
                server_id TEXT NOT NULL, tool_name TEXT NOT NULL, description TEXT,
                input_schema JSONB NOT NULL DEFAULT '{}'::jsonb, enabled BOOLEAN NOT NULL DEFAULT true,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(server_id, tool_name)
            )""",
            """CREATE TABLE IF NOT EXISTS mcp_tool_approval (
                server_id TEXT NOT NULL, tool_name TEXT NOT NULL, agent_code TEXT NOT NULL,
                allowed BOOLEAN NOT NULL, reason TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY(server_id, tool_name, agent_code)
            )""",
            """CREATE TABLE IF NOT EXISTS plugin_marketplace_install (
                install_id TEXT PRIMARY KEY, package_id TEXT NOT NULL, version TEXT NOT NULL,
                source_json JSONB NOT NULL, approval_status TEXT NOT NULL DEFAULT 'pending',
                approved_by TEXT, approved_at TIMESTAMPTZ, approval_reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(package_id, version)
            )""",
            """CREATE TABLE IF NOT EXISTS memory_record (
                memory_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, scope TEXT NOT NULL,
                content_json JSONB NOT NULL, source_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                confirmed_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, superseded_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS memory_lifecycle_event (
                event_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL REFERENCES memory_record(memory_id) ON DELETE CASCADE,
                action TEXT NOT NULL, actor_id TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS llm_call_trace (
                trace_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, task_id TEXT,
                actor_id TEXT, role TEXT, model TEXT NOT NULL, prompt_version TEXT,
                fallback_used BOOLEAN NOT NULL DEFAULT false, fallback_reason TEXT,
                latency_ms INTEGER, token_usage JSONB, status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS llm_prompt_version (
                prompt_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                template TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(name, version)
            )""",
            """CREATE TABLE IF NOT EXISTS benchmark_run (
                run_id TEXT PRIMARY KEY, dataset_version TEXT NOT NULL, config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS benchmark_result (
                result_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES benchmark_run(run_id) ON DELETE CASCADE,
                case_id TEXT NOT NULL, result_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(run_id, case_id)
            )""",
            """CREATE TABLE IF NOT EXISTS rag_document (
                document_id TEXT PRIMARY KEY, collection TEXT NOT NULL, path TEXT NOT NULL,
                version TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(collection, path, version)
            )""",
            """CREATE TABLE IF NOT EXISTS rag_chunk (
                chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES rag_document(document_id) ON DELETE CASCADE,
                content TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding vector, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS rag_gold_case (
                case_id TEXT PRIMARY KEY, dataset_version TEXT NOT NULL, case_json JSONB NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_pg_mcp_call_request ON mcp_tool_call_log(request_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_memory_scope ON memory_record(scope, expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_llm_request ON llm_call_trace(request_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_rag_document_collection ON rag_document(collection, path)",
            "CREATE INDEX IF NOT EXISTS idx_pg_skill_execution_task ON skill_execution_log(task_id, created_at)",
        )
        with self.connection() as conn, conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute("INSERT INTO jaycode_schema_version(version) VALUES (2) ON CONFLICT(version) DO NOTHING")

    def save_audit(self, record: dict[str, Any]) -> None:
        audit = {"audit_id": record.get("audit_id") or f"audit_{uuid4().hex}", **record}
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO security_audit_log(audit_id, request_id, actor_id, role, action, resource_type, resource_id, status, metadata_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (audit["audit_id"], audit.get("request_id", ""), audit.get("actor_id", "unknown"), audit.get("role", "unknown"), audit.get("action", "unknown"), audit.get("resource_type", "api"), audit.get("resource_id"), audit.get("status", "unknown"), json.dumps(audit.get("metadata", {}), ensure_ascii=False), audit.get("created_at") or utc_now_iso()),
            )

    def create_task(self, task_id: str, goal: str, project_path: str | None, status: str, context: dict[str, Any] | None = None, input_state: dict[str, Any] | None = None) -> dict[str, Any] | None:
        context = context or {}
        with self.connection() as conn:
            if context.get("idempotency_key"):
                existing = conn.execute("SELECT * FROM agent_task WHERE idempotency_key = %s", (context["idempotency_key"],)).fetchone()
                if existing:
                    return dict(existing)
            conn.execute(
                "INSERT INTO agent_task(task_id, goal, project_path, status, created_at, updated_at, request_id, actor_id, role, idempotency_key, input_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING",
                (task_id, goal, project_path, status, utc_now_iso(), utc_now_iso(), context.get("request_id"), context.get("actor_id"), context.get("role"), context.get("idempotency_key"), json.dumps(input_state or {}, ensure_ascii=False)),
            )
            if context.get("idempotency_key"):
                existing = conn.execute("SELECT * FROM agent_task WHERE idempotency_key = %s", (context["idempotency_key"],)).fetchone()
                return dict(existing) if existing and existing["task_id"] != task_id else None
        return None

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM agent_task WHERE task_id = %s", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM agent_task ORDER BY created_at DESC LIMIT %s OFFSET %s", (max(1, min(limit, 1000)), max(0, offset))).fetchall()
        return [dict(row) for row in rows]

    def get_task_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM agent_task WHERE idempotency_key = %s", (key,)).fetchone()
        return dict(row) if row else None

    def get_task_input(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        value = task.get("input_json") if task else {}
        return value if isinstance(value, dict) else json.loads(value or "{}")

    def update_task(self, task_id: str, status: str, final_report: str | None = None, *, retry: bool = False, resume: bool = False) -> None:
        transitions = {"created": {"queued", "running", "cancelled", "failed"}, "queued": {"running", "cancelled", "failed"}, "running": {"completed", "waiting_review", "paused", "failed", "cancelled", "queued"}, "waiting_review": {"running", "queued", "completed", "cancelled", "rejected", "paused"}, "paused": {"queued", "running", "cancelled", "failed"}, "failed": {"queued", "running"}, "cancelled": {"queued"}}
        with self.connection() as conn:
            row = conn.execute("SELECT status FROM agent_task WHERE task_id = %s FOR UPDATE", (task_id,)).fetchone()
            if not row:
                raise ValueError(f"Task `{task_id}` does not exist.")
            if status != row["status"] and status not in transitions.get(row["status"], set()):
                raise ValueError(f"Invalid task status transition: {row['status']} -> {status}")
            conn.execute("UPDATE agent_task SET status=%s, final_report=COALESCE(%s, final_report), updated_at=%s, retry_count=retry_count+%s, resume_count=resume_count+%s, execution_version=execution_version+1 WHERE task_id=%s", (status, final_report, utc_now_iso(), int(retry), int(resume), task_id))

    def append_event(self, event: dict[str, Any]) -> None:
        task_id = str(event["task_id"])
        with self.connection() as conn:
            conn.execute("SELECT task_id FROM agent_task WHERE task_id=%s FOR UPDATE", (task_id,))
            seq = conn.execute("SELECT COALESCE(MAX(event_seq),0)+1 AS seq FROM agent_task_event WHERE task_id=%s", (task_id,)).fetchone()["seq"]
            conn.execute(
                "INSERT INTO agent_task_event(event_id, task_id, event_type, node, agent, status, content, data_json, event_seq, execution_version, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT(event_id) DO NOTHING",
                (event.get("event_id") or f"evt_{uuid4().hex}", task_id, event.get("type", "event"), event.get("node"), event.get("agent"), event.get("status"), event.get("content"), json.dumps(event.get("data", {}), ensure_ascii=False), seq, int(event.get("execution_version") or 1), event.get("timestamp") or utc_now_iso()),
            )

    def get_events(self, task_id: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT event_id, task_id, event_type AS type, node, agent, status, content, data_json, created_at AS timestamp, event_seq FROM agent_task_event WHERE task_id=%s ORDER BY event_seq", (task_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            data = item.pop("data_json")
            item["data"] = data if isinstance(data, dict) else json.loads(data or "{}")
            result.append(item)
        return result

    def get_events_after(self, task_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        return [event for event in self.get_events(task_id) if int(event.get("event_seq") or 0) > after_seq]

    def save_artifact(self, task_id: str, artifact_type: str, name: str, content: Any) -> None:
        with self.connection() as conn:
            row = conn.execute("SELECT execution_version FROM agent_task WHERE task_id=%s", (task_id,)).fetchone()
            conn.execute("INSERT INTO agent_task_artifact(task_id, artifact_type, name, content_json, execution_version, created_at) VALUES (%s,%s,%s,%s::jsonb,%s,%s)", (task_id, artifact_type, name, json.dumps(content, ensure_ascii=False), int(row["execution_version"]), utc_now_iso()))

    def get_artifacts(self, task_id: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT artifact_type, name, content_json, created_at FROM agent_task_artifact WHERE task_id=%s ORDER BY id", (task_id,)).fetchall()
        return [{**dict(row), "content": row["content_json"] if isinstance(row["content_json"], (dict, list)) else json.loads(row["content_json"] or "null")} for row in rows]

    def save_task_bundle(self, task_id: str, status: str, final_report: str | None, artifacts: list[tuple[str, str, Any]], events: list[dict[str, Any]], *, error_code: str | None = None, error_message: str | None = None) -> None:
        now = utc_now_iso()
        transitions = {"created": {"queued", "running", "cancelled", "failed"}, "queued": {"running", "cancelled", "failed"}, "running": {"completed", "waiting_review", "paused", "failed", "cancelled", "queued"}, "waiting_review": {"running", "queued", "completed", "cancelled", "rejected", "paused"}, "paused": {"queued", "running", "cancelled", "failed"}, "failed": {"queued", "running"}, "cancelled": {"queued"}}
        with self.connection() as conn:
            row = conn.execute("SELECT status, execution_version FROM agent_task WHERE task_id=%s FOR UPDATE", (task_id,)).fetchone()
            if not row:
                raise ValueError(f"Task `{task_id}` does not exist.")
            if status != row["status"] and status not in transitions.get(row["status"], set()):
                raise ValueError(f"Invalid task status transition: {row['status']} -> {status}")
            version = int(row["execution_version"]) + 1
            conn.execute("UPDATE agent_task SET status=%s, final_report=COALESCE(%s,final_report), updated_at=%s, execution_version=%s, worker_id=NULL, lease_until=NULL, heartbeat_at=NULL, error_code=%s, error_message=%s, failed_at=%s WHERE task_id=%s", (status, final_report, now, version, error_code if status == "failed" else None, error_message if status == "failed" else None, now if status == "failed" else None, task_id))
            for artifact_type, name, content in artifacts:
                conn.execute("INSERT INTO agent_task_artifact(task_id,artifact_type,name,content_json,execution_version,created_at) VALUES (%s,%s,%s,%s::jsonb,%s,%s)", (task_id, artifact_type, name, json.dumps(content, ensure_ascii=False), version, now))
            for event in events:
                sequence = conn.execute("SELECT COALESCE(MAX(event_seq),0)+1 AS seq FROM agent_task_event WHERE task_id=%s", (task_id,)).fetchone()["seq"]
                conn.execute("INSERT INTO agent_task_event(event_id,task_id,event_type,node,agent,status,content,data_json,event_seq,execution_version,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT(event_id) DO NOTHING", (event.get("event_id") or f"evt_{uuid4().hex}", task_id, event.get("type", "event"), event.get("node"), event.get("agent"), event.get("status"), event.get("content"), json.dumps(event.get("data", {}), ensure_ascii=False), sequence, version, event.get("timestamp") or now))

    def claim_next_task(self, worker_id: str, lease_seconds: int = 30) -> dict[str, Any] | None:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=max(1, lease_seconds))
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM agent_task WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
            if not row:
                return None
            conn.execute("UPDATE agent_task SET status='running', worker_id=%s, lease_until=%s, heartbeat_at=%s, attempt=attempt+1, updated_at=%s WHERE task_id=%s", (worker_id, lease_until.isoformat(), now.isoformat(), now.isoformat(), row["task_id"]))
            claimed = dict(row)
            claimed.update({"status": "running", "worker_id": worker_id, "attempt": int(row["attempt"]) + 1})
            return claimed

    def heartbeat_task(self, task_id: str, worker_id: str, lease_seconds: int = 30) -> bool:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        with self.connection() as conn:
            result = conn.execute("UPDATE agent_task SET heartbeat_at=%s, lease_until=%s, updated_at=%s WHERE task_id=%s AND worker_id=%s AND status='running'", ((now).isoformat(), (now + timedelta(seconds=lease_seconds)).isoformat(), now.isoformat(), task_id, worker_id))
        return result.rowcount == 1

    def cancel_task(self, task_id: str) -> bool:
        now = utc_now_iso()
        event_id = f"evt_{uuid4().hex}"
        with self.connection() as conn:
            row = conn.execute("SELECT status, execution_version FROM agent_task WHERE task_id=%s FOR UPDATE", (task_id,)).fetchone()
            if not row or row["status"] in {"completed", "failed", "cancelled", "rejected"}:
                return False
            conn.execute("UPDATE agent_task SET status='cancelled', worker_id=NULL, lease_until=NULL, heartbeat_at=NULL, updated_at=%s, execution_version=execution_version+1 WHERE task_id=%s", (now, task_id))
            seq = conn.execute("SELECT COALESCE(MAX(event_seq),0)+1 AS seq FROM agent_task_event WHERE task_id=%s", (task_id,)).fetchone()["seq"]
            conn.execute("INSERT INTO agent_task_event(event_id,task_id,event_type,status,content,data_json,event_seq,execution_version,created_at) VALUES (%s,%s,'task_cancelled','cancelled','Task cancellation requested.','{}'::jsonb,%s,%s,%s)", (event_id, task_id, seq, int(row["execution_version"])+1, now))
        return True

    def recover_expired_task_ids(self) -> list[str]:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        recovered = []
        with self.connection() as conn:
            rows = conn.execute("SELECT task_id, worker_id FROM agent_task WHERE status='running' AND lease_until < %s FOR UPDATE SKIP LOCKED", (now,)).fetchall()
            for row in rows:
                task_id = str(row["task_id"])
                task = conn.execute("SELECT execution_version FROM agent_task WHERE task_id=%s", (task_id,)).fetchone()
                version = int(task["execution_version"]) + 1
                conn.execute("UPDATE agent_task SET status='queued', worker_id=NULL, lease_until=NULL, heartbeat_at=NULL, updated_at=%s, execution_version=%s WHERE task_id=%s", (now, version, task_id))
                seq = conn.execute("SELECT COALESCE(MAX(event_seq),0)+1 AS seq FROM agent_task_event WHERE task_id=%s", (task_id,)).fetchone()["seq"]
                conn.execute("INSERT INTO agent_task_event(event_id,task_id,event_type,status,content,data_json,event_seq,execution_version,created_at) VALUES (%s,%s,'worker_recovered','queued',%s,%s::jsonb,%s,%s,%s)", (f"evt_recovered_{task_id}_{version}", task_id, f"Lease expired for worker {row['worker_id'] or 'unknown'}.", json.dumps({"worker_id": row["worker_id"]}), seq, version, now))
                recovered.append(task_id)
        return recovered
