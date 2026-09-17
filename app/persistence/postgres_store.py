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

from app.core.config import settings
from app.harness.events import utc_now_iso
from app.persistence.postgres_migrations import (
    PostgresMigration,
    apply_postgres_migrations,
    assert_pgvector_available,
)


def _postgres_timestamp(value: Any) -> Any:
    """Translate the legacy SQLite timestamp text into a timezone-aware value."""
    if not isinstance(value, str):
        return value
    from datetime import datetime

    from app.harness.events import BEIJING_TZ

    normalized = value.replace(", ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return parsed.replace(tzinfo=BEIJING_TZ) if parsed.tzinfo is None else parsed


class PostgresTaskStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL store")
        self.database_url = database_url

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - dependency is optional at runtime
            raise RuntimeError("psycopg is required for PostgreSQL store") from exc
        # Every adapter method consumes rows by column name. psycopg defaults
        # to tuples, which made the first real PostgreSQL contract test fail
        # after its INSERT succeeded.
        with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=10) as conn:
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
            "CREATE INDEX IF NOT EXISTS idx_pg_audit_actor_created ON security_audit_log(actor_id, created_at)",
            """CREATE TABLE IF NOT EXISTS agent_worker (
                worker_id TEXT PRIMARY KEY, pid INTEGER NOT NULL, started_at TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL, status TEXT NOT NULL, active_task_id TEXT,
                restart_count INTEGER NOT NULL DEFAULT 0
            )""",
        )
        with self.connection() as conn:
            apply_postgres_migrations(conn, (PostgresMigration(1, "core-task-audit-worker", statements),))

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
            "ALTER TABLE workflow_definition ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE workflow_definition ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE workflow_definition ADD COLUMN IF NOT EXISTS nodes_json JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE workflow_definition ADD COLUMN IF NOT EXISTS edges_json JSONB NOT NULL DEFAULT '[]'::jsonb",
            """CREATE TABLE IF NOT EXISTS human_review_action (
                review_id TEXT PRIMARY KEY, task_id TEXT REFERENCES agent_task(task_id),
                actor_id TEXT NOT NULL, action TEXT NOT NULL, payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE human_review_action ADD COLUMN IF NOT EXISTS comment TEXT",
            """CREATE TABLE IF NOT EXISTS learning_plan (
                plan_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, topic TEXT NOT NULL, level TEXT NOT NULL,
                status TEXT NOT NULL, plan_json JSONB NOT NULL, quiz_json JSONB NOT NULL,
                report_markdown TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS skill_registry (
                skill_id TEXT PRIMARY KEY, version TEXT NOT NULL, manifest_json JSONB NOT NULL,
                approval_status TEXT NOT NULL DEFAULT 'pending', updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(skill_id, version)
            )""",
            """CREATE TABLE IF NOT EXISTS skill_plugin (
                plugin_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                source_type TEXT NOT NULL, source_url TEXT, author TEXT, description TEXT,
                enabled BOOLEAN NOT NULL DEFAULT true, installed_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS skill_version_snapshot (
                id BIGSERIAL PRIMARY KEY, skill_code TEXT NOT NULL, plugin_id TEXT NOT NULL,
                version TEXT NOT NULL, snapshot_json JSONB NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(skill_code,plugin_id,version)
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
            "ALTER TABLE skill_approval ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE skill_execution_log ADD COLUMN IF NOT EXISTS agent_code TEXT",
            """CREATE TABLE IF NOT EXISTS mcp_server_config (
                server_id TEXT PRIMARY KEY, command TEXT NOT NULL, args_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                env_json JSONB NOT NULL DEFAULT '{}'::jsonb, enabled BOOLEAN NOT NULL DEFAULT false,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE mcp_server_config ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mcp_server_config ADD COLUMN IF NOT EXISTS transport TEXT NOT NULL DEFAULT 'stdio'",
            "ALTER TABLE mcp_server_config ADD COLUMN IF NOT EXISTS url TEXT",
            "ALTER TABLE mcp_server_config ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE mcp_server_config ADD COLUMN IF NOT EXISTS last_error TEXT",
            "ALTER TABLE mcp_server_config ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS mcp_tool_call_log (
                call_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, actor_id TEXT NOT NULL, role TEXT NOT NULL,
                server_id TEXT NOT NULL, tool_name TEXT NOT NULL, status TEXT NOT NULL, exit_code INTEGER,
                latency_ms INTEGER, error_message TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE mcp_tool_call_log ADD COLUMN IF NOT EXISTS agent_code TEXT",
            "ALTER TABLE mcp_tool_call_log ADD COLUMN IF NOT EXISTS input_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE mcp_tool_call_log ADD COLUMN IF NOT EXISTS output_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE mcp_tool_call_log ADD COLUMN IF NOT EXISTS command_summary TEXT NOT NULL DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS mcp_tool_registry (
                server_id TEXT NOT NULL, tool_name TEXT NOT NULL, description TEXT,
                input_schema JSONB NOT NULL DEFAULT '{}'::jsonb, enabled BOOLEAN NOT NULL DEFAULT true,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(server_id, tool_name)
            )""",
            "ALTER TABLE mcp_tool_registry ADD COLUMN IF NOT EXISTS tool_id TEXT",
            "ALTER TABLE mcp_tool_registry ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'available'",
            "ALTER TABLE mcp_tool_registry ADD COLUMN IF NOT EXISTS discovered_at TEXT NOT NULL DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS mcp_tool_approval (
                server_id TEXT NOT NULL, tool_name TEXT NOT NULL, agent_code TEXT NOT NULL,
                allowed BOOLEAN NOT NULL, reason TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY(server_id, tool_name, agent_code)
            )""",
            "ALTER TABLE mcp_tool_approval ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS plugin_marketplace_install (
                install_id TEXT PRIMARY KEY, package_id TEXT NOT NULL, version TEXT NOT NULL,
                source_json JSONB NOT NULL, approval_status TEXT NOT NULL DEFAULT 'pending',
                approved_by TEXT, approved_at TIMESTAMPTZ, approval_reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(package_id, version)
            )""",
            "ALTER TABLE plugin_marketplace_install DROP CONSTRAINT IF EXISTS plugin_marketplace_install_package_id_version_key",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS package_type TEXT NOT NULL DEFAULT 'skill'",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS source_url TEXT",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending'",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS summary_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS manifest_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS error_message TEXT",
            "ALTER TABLE plugin_marketplace_install ADD COLUMN IF NOT EXISTS installed_at TEXT NOT NULL DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS memory_record (
                memory_id TEXT PRIMARY KEY, actor_id TEXT, scope TEXT NOT NULL,
                scope_id TEXT NOT NULL DEFAULT 'local-user', memory_type TEXT NOT NULL DEFAULT 'fact',
                memory_key TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '', confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'candidate', source_type TEXT NOT NULL DEFAULT 'conversation',
                source_ref TEXT, source_task_id TEXT, confirmed_by TEXT, superseded_by TEXT, revoked_at TEXT,
                extraction_source TEXT NOT NULL DEFAULT 'rule_fallback', quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                quality_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
                retention_policy TEXT NOT NULL DEFAULT 'review_90d', expires_at TEXT, conflict_with TEXT,
                rag_path TEXT, confirmed_at TEXT, content_json JSONB, source_json JSONB,
                created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
            )""",
            """CREATE TABLE IF NOT EXISTS memory_lifecycle_event (
                event_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
                action TEXT NOT NULL, actor_id TEXT, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS llm_call_trace (
                trace_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, task_id TEXT,
                actor_id TEXT, role TEXT, model TEXT NOT NULL, prompt_version TEXT,
                fallback_used BOOLEAN NOT NULL DEFAULT false, fallback_reason TEXT,
                latency_ms INTEGER, token_usage JSONB, status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE llm_call_trace ADD COLUMN IF NOT EXISTS agent TEXT NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE llm_call_trace ADD COLUMN IF NOT EXISTS input_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE llm_call_trace ADD COLUMN IF NOT EXISTS output_text TEXT",
            "ALTER TABLE llm_call_trace ADD COLUMN IF NOT EXISTS error_message TEXT",
            "ALTER TABLE llm_call_trace ADD COLUMN IF NOT EXISTS token_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            """CREATE TABLE IF NOT EXISTS llm_prompt_version (
                prompt_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                template TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(name, version)
            )""",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS agent TEXT NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS prompt_family TEXT NOT NULL DEFAULT 'default'",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS prompt_version TEXT NOT NULL DEFAULT 'v1'",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS system_suffix TEXT",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE llm_prompt_version ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
            """CREATE TABLE IF NOT EXISTS benchmark_run (
                run_id TEXT PRIMARY KEY, dataset_version TEXT NOT NULL, config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE benchmark_run ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE benchmark_run ADD COLUMN IF NOT EXISTS benchmark_type TEXT NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE benchmark_run ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'queued'",
            "ALTER TABLE benchmark_run ADD COLUMN IF NOT EXISTS summary_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE benchmark_run ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE benchmark_run ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
            """CREATE TABLE IF NOT EXISTS benchmark_result (
                result_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES benchmark_run(run_id) ON DELETE CASCADE,
                case_id TEXT NOT NULL, result_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(run_id, case_id)
            )""",
            "ALTER TABLE benchmark_result DROP CONSTRAINT IF EXISTS benchmark_result_run_id_case_id_key",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS server_id TEXT",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS tool_name TEXT",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS iteration INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS latency_ms INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS error_message TEXT",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS input_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE benchmark_result ADD COLUMN IF NOT EXISTS output_json JSONB NOT NULL DEFAULT '{}'::jsonb",
            """CREATE TABLE IF NOT EXISTS rag_document (
                id BIGSERIAL PRIMARY KEY, collection TEXT NOT NULL, path TEXT NOT NULL,
                size INTEGER, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                content_hash TEXT, version INTEGER NOT NULL DEFAULT 1,
                is_current BOOLEAN NOT NULL DEFAULT TRUE, valid_to TIMESTAMPTZ,
                acl_json JSONB NOT NULL DEFAULT '["*"]'::jsonb
            )""",
            f"""CREATE TABLE IF NOT EXISTS rag_chunk (
                id BIGSERIAL PRIMARY KEY, collection TEXT NOT NULL, chunk_id TEXT NOT NULL,
                path TEXT NOT NULL, content TEXT NOT NULL,
                metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector({settings.jaycode_embedding_dim}) NOT NULL,
                embedding_source TEXT NOT NULL, document_version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS rag_gold_case (
                case_id TEXT PRIMARY KEY, collection TEXT NOT NULL, question TEXT NOT NULL,
                expected_chunk_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                expected_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_document_version ON rag_document(collection, path, version)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_chunk_version ON rag_chunk(collection, chunk_id, document_version)",
            "CREATE INDEX IF NOT EXISTS idx_pg_mcp_call_request ON mcp_tool_call_log(request_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_memory_scope ON memory_record(scope, expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_llm_request ON llm_call_trace(request_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_rag_document_collection ON rag_document(collection, path)",
            "CREATE INDEX IF NOT EXISTS idx_pg_skill_execution_task ON skill_execution_log(task_id, created_at)",
        )
        with self.connection() as conn:
            assert_pgvector_available(conn)
            apply_postgres_migrations(conn, (PostgresMigration(2, "all-domain-schema", statements),))
        legacy_statements = (
            """CREATE TABLE IF NOT EXISTS agent_task_node_state (
                task_id TEXT NOT NULL, node_id TEXT NOT NULL, state TEXT NOT NULL,
                attempt INTEGER NOT NULL, error_message TEXT, output_json JSONB,
                started_at TEXT, finished_at TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY(task_id, node_id)
            )""",
            """CREATE TABLE IF NOT EXISTS benchmark_comparison (
                comparison_id TEXT PRIMARY KEY, current_run_id TEXT NOT NULL,
                baseline_run_id TEXT, regression_status TEXT NOT NULL,
                threshold_json JSONB NOT NULL, delta_json JSONB NOT NULL, created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS marketplace_install_snapshot (
                snapshot_id TEXT PRIMARY KEY, package_id TEXT NOT NULL, package_type TEXT NOT NULL,
                manifest_json JSONB NOT NULL, state_json JSONB NOT NULL, created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS platform_approval (
                approval_id TEXT PRIMARY KEY, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
                version_id TEXT, actor_id TEXT NOT NULL, decision TEXT NOT NULL,
                reason TEXT, created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS platform_query (
                query_id TEXT PRIMARY KEY, query_type TEXT NOT NULL, actor_id TEXT NOT NULL,
                task_id TEXT, input_json JSONB NOT NULL, result_json JSONB NOT NULL,
                score_json JSONB NOT NULL, created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS platform_version (
                version_id TEXT PRIMARY KEY, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
                version TEXT NOT NULL, status TEXT NOT NULL, manifest_json JSONB NOT NULL,
                created_by TEXT, created_at TEXT NOT NULL, activated_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS rag_evaluation_run (
                run_id TEXT PRIMARY KEY, collection TEXT, actor_id TEXT NOT NULL,
                case_count INTEGER NOT NULL, hit_count INTEGER NOT NULL,
                recall_at_8 DOUBLE PRECISION NOT NULL, mrr DOUBLE PRECISION NOT NULL,
                result_json JSONB NOT NULL, created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS schema_migration (
                version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_pg_node_state_task ON agent_task_node_state(task_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_platform_query_task ON platform_query(task_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_pg_rag_evaluation_collection ON rag_evaluation_run(collection, created_at)",
        )
        with self.connection() as conn:
            apply_postgres_migrations(conn, (PostgresMigration(3, "legacy-domain-schema", legacy_statements),))

    def save_audit(self, record: dict[str, Any]) -> None:
        audit = {"audit_id": record.get("audit_id") or f"audit_{uuid4().hex}", **record}
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO security_audit_log(audit_id, request_id, actor_id, role, action, resource_type, resource_id, status, metadata_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (audit["audit_id"], audit.get("request_id", ""), audit.get("actor_id", "unknown"), audit.get("role", "unknown"), audit.get("action", "unknown"), audit.get("resource_type", "api"), audit.get("resource_id"), audit.get("status", "unknown"), json.dumps(audit.get("metadata", {}), ensure_ascii=False), audit.get("created_at") or utc_now_iso()),
            )

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
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO security_audit_log(
                    audit_id,request_id,actor_id,role,action,resource_type,resource_id,status,metadata_json,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (
                    audit["audit_id"], audit["request_id"], audit["actor_id"], audit["role"],
                    audit["action"], audit["resource_type"], audit["resource_id"], audit["status"],
                    json.dumps(audit["metadata"], ensure_ascii=False), audit["created_at"],
                ),
            )
        return audit

    def list_security_audits(
        self, limit: int = 100, actor_id: str | None = None, role: str | None = None,
        action: str | None = None, status: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = [("actor_id", actor_id), ("role", role), ("action", action), ("status", status)]
        active = [(field, value) for field, value in filters if value]
        where = " WHERE " + " AND ".join(f"{field}=%s" for field, _ in active) if active else ""
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM security_audit_log{where} ORDER BY created_at DESC LIMIT %s",
                (*[value for _, value in active], max(1, min(limit, 1000))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = item.pop("metadata_json") or {}
            result.append(item)
        return result

    def register_worker(self, worker_id: str, pid: int) -> None:
        now = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO agent_worker(worker_id,pid,started_at,last_heartbeat,status,active_task_id)
                   VALUES (%s,%s,%s,%s,'running',NULL)
                   ON CONFLICT(worker_id) DO UPDATE SET pid=EXCLUDED.pid,started_at=EXCLUDED.started_at,
                   last_heartbeat=EXCLUDED.last_heartbeat,status='running',active_task_id=NULL""",
                (worker_id, pid, now, now),
            )

    def heartbeat_worker(self, worker_id: str, active_task_id: str | None = None) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE agent_worker SET last_heartbeat=%s,status='running',active_task_id=%s WHERE worker_id=%s",
                (utc_now_iso(), active_task_id, worker_id),
            )

    def unregister_worker(self, worker_id: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE agent_worker SET last_heartbeat=%s,status='stopped',active_task_id=NULL WHERE worker_id=%s",
                (utc_now_iso(), worker_id),
            )

    def list_workers(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM agent_worker ORDER BY started_at").fetchall()
        return [dict(row) for row in rows]

    def save_workflow(
        self, workflow_id: str, name: str, description: str | None,
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connection() as conn:
            old = conn.execute("SELECT created_at FROM workflow_definition WHERE workflow_id=%s", (workflow_id,)).fetchone()
            created_at = old["created_at"] if old else _postgres_timestamp(now)
            nodes_json = json.dumps(nodes, ensure_ascii=False)
            edges_json = json.dumps(edges, ensure_ascii=False)
            conn.execute(
                """INSERT INTO workflow_definition(workflow_id,name,description,nodes_json,edges_json,definition_json,created_at,updated_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
                   ON CONFLICT(workflow_id) DO UPDATE SET name=EXCLUDED.name,description=EXCLUDED.description,
                   nodes_json=EXCLUDED.nodes_json,edges_json=EXCLUDED.edges_json,definition_json=EXCLUDED.definition_json,
                   version=workflow_definition.version+1,updated_at=EXCLUDED.updated_at""",
                (workflow_id, name, description, nodes_json, edges_json,
                 json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False), created_at, _postgres_timestamp(now)),
            )
        return self.get_workflow(workflow_id) or {}

    @staticmethod
    def _workflow_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["nodes"] = item.pop("nodes_json") or []
        item["edges"] = item.pop("edges_json") or []
        return item

    def list_workflows(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT workflow_id,name,description,nodes_json,edges_json,created_at,updated_at FROM workflow_definition ORDER BY updated_at DESC"
            ).fetchall()
        return [self._workflow_dict(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT workflow_id,name,description,nodes_json,edges_json,created_at,updated_at FROM workflow_definition WHERE workflow_id=%s",
                (workflow_id,),
            ).fetchone()
        return self._workflow_dict(row) if row else None

    def record_review_action(
        self, task_id: str, action: str, comment: str | None = None, actor_id: str = "system-agent"
    ) -> dict[str, Any]:
        now = utc_now_iso()
        review_id = f"review_{uuid4().hex}"
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO human_review_action(review_id,task_id,actor_id,action,comment,payload_json,created_at) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)",
                (review_id, task_id, actor_id, action, comment, json.dumps({"comment": comment}, ensure_ascii=False), _postgres_timestamp(now)),
            )
        return {"review_id": review_id, "task_id": task_id, "action": action, "comment": comment, "created_at": now}

    def save_learning_plan(
        self, plan_id: str, task_id: str, topic: str, level: str,
        plan: list[dict[str, Any]], quiz: list[dict[str, Any]], report_markdown: str,
        status: str = "active",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connection() as conn:
            old = conn.execute("SELECT created_at FROM learning_plan WHERE plan_id=%s", (plan_id,)).fetchone()
            conn.execute(
                """INSERT INTO learning_plan(plan_id,task_id,topic,level,status,plan_json,quiz_json,report_markdown,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                   ON CONFLICT(plan_id) DO UPDATE SET task_id=EXCLUDED.task_id,topic=EXCLUDED.topic,
                   level=EXCLUDED.level,status=EXCLUDED.status,plan_json=EXCLUDED.plan_json,
                   quiz_json=EXCLUDED.quiz_json,report_markdown=EXCLUDED.report_markdown,updated_at=EXCLUDED.updated_at""",
                (plan_id, task_id, topic, level, status, json.dumps(plan, ensure_ascii=False), json.dumps(quiz, ensure_ascii=False), report_markdown, old["created_at"] if old else now, now),
            )
        return self.get_learning_plan(plan_id) or {}

    @staticmethod
    def _learning_plan_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["plan"] = item.pop("plan_json") or []
        item["quiz"] = item.pop("quiz_json") or []
        return item

    def list_learning_plans(self, task_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT plan_id,task_id,topic,level,status,plan_json,quiz_json,report_markdown,created_at,updated_at FROM learning_plan WHERE (%s::text IS NULL OR task_id=%s) ORDER BY created_at DESC",
                (task_id, task_id),
            ).fetchall()
        return [self._learning_plan_dict(row) for row in rows]

    def get_learning_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT plan_id,task_id,topic,level,status,plan_json,quiz_json,report_markdown,created_at,updated_at FROM learning_plan WHERE plan_id=%s",
                (plan_id,),
            ).fetchone()
        return self._learning_plan_dict(row) if row else None

    def update_learning_plan_status(self, plan_id: str, status: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.execute("UPDATE learning_plan SET status=%s,updated_at=%s WHERE plan_id=%s", (status, utc_now_iso(), plan_id))
        return self.get_learning_plan(plan_id)

    @staticmethod
    def _prompt_family(prompt_version: str) -> str:
        parts = prompt_version.split(".")
        if len(parts) > 1 and parts[-1].startswith("v") and parts[-1][1:].isdigit():
            return ".".join(parts[:-1])
        return prompt_version

    def save_llm_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        record = {
            **trace,
            "trace_id": trace.get("trace_id") or f"llm_{uuid4().hex}",
            "agent": trace.get("agent") or "unknown",
            "prompt_version": trace.get("prompt_version") or "v1",
            "model": trace.get("model") or "unknown",
            "input": trace.get("input") or {},
            "output": trace.get("output"),
            "fallback_used": bool(trace.get("fallback_used")),
            "latency_ms": int(trace.get("latency_ms") or 0),
            "token_usage": trace.get("token_usage") or {},
            "request_id": trace.get("request_id") or "",
            "status": trace.get("status") or ("failed" if trace.get("error_message") else "completed"),
            "created_at": trace.get("created_at") or utc_now_iso(),
        }
        output_text = record["output"] if isinstance(record["output"], str) else json.dumps(record["output"], ensure_ascii=False)
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO llm_call_trace(trace_id,agent,prompt_version,model,input_json,output_text,
                   fallback_used,error_message,latency_ms,token_usage_json,request_id,actor_id,role,created_at,
                   fallback_reason,status,token_usage)
                   VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(trace_id) DO NOTHING""",
                (
                    record["trace_id"], record["agent"], record["prompt_version"], record["model"],
                    json.dumps(record["input"], ensure_ascii=False), output_text, record["fallback_used"],
                    record.get("error_message"), record["latency_ms"],
                    json.dumps(record["token_usage"], ensure_ascii=False), record["request_id"],
                    record.get("actor_id"), record.get("role"), _postgres_timestamp(record["created_at"]),
                    record.get("fallback_reason"), record["status"],
                    json.dumps(record["token_usage"], ensure_ascii=False),
                ),
            )
        return record

    def list_llm_traces(self, limit: int = 50, agent: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT trace_id,agent,prompt_version,model,input_json,output_text,fallback_used,
                   error_message,latency_ms,token_usage_json,request_id,actor_id,role,created_at,status
                   FROM llm_call_trace WHERE (%s::text IS NULL OR agent=%s) ORDER BY created_at DESC LIMIT %s""",
                (agent, agent, max(1, min(limit, 200))),
            ).fetchall()
        traces = []
        for row in rows:
            item = dict(row)
            item["input"] = item.pop("input_json") or {}
            item["output"] = item.pop("output_text")
            item["token_usage"] = item.pop("token_usage_json") or {}
            item["fallback_used"] = bool(item["fallback_used"])
            traces.append(item)
        return traces

    def upsert_prompt_version(self, prompt: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        agent = str(prompt.get("agent") or "unknown")
        version = str(prompt.get("prompt_version") or "v1")
        family = str(prompt.get("prompt_family") or self._prompt_family(version))
        with self.connection() as conn:
            old = conn.execute(
                "SELECT created_at FROM llm_prompt_version WHERE agent=%s AND prompt_version=%s FOR UPDATE",
                (agent, version),
            ).fetchone()
            created = old["created_at"] if old else _postgres_timestamp(now)
            suffix = prompt.get("system_suffix") or ""
            conn.execute(
                """INSERT INTO llm_prompt_version(name,version,template,prompt_id,agent,prompt_family,
                   prompt_version,title,description,system_suffix,is_active,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(name,version) DO UPDATE SET template=EXCLUDED.template,
                   title=EXCLUDED.title,description=EXCLUDED.description,system_suffix=EXCLUDED.system_suffix,
                   is_active=EXCLUDED.is_active,updated_at=EXCLUDED.updated_at""",
                (
                    agent, version, suffix, f"prompt_{agent}_{version}", agent, family, version,
                    str(prompt.get("title") or version), prompt.get("description"), suffix,
                    bool(prompt.get("is_active")), created, _postgres_timestamp(now),
                ),
            )
        return self.get_prompt_version(agent, version) or {}

    def set_active_prompt_version(self, agent: str, prompt_version: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT prompt_family FROM llm_prompt_version WHERE agent=%s AND prompt_version=%s FOR UPDATE",
                (agent, prompt_version),
            ).fetchone()
            if not row:
                return None
            now = _postgres_timestamp(utc_now_iso())
            conn.execute(
                "UPDATE llm_prompt_version SET is_active=false,updated_at=%s WHERE agent=%s AND prompt_family=%s",
                (now, agent, row["prompt_family"]),
            )
            conn.execute(
                "UPDATE llm_prompt_version SET is_active=true,updated_at=%s WHERE agent=%s AND prompt_version=%s",
                (now, agent, prompt_version),
            )
        return self.get_prompt_version(agent, prompt_version)

    @staticmethod
    def _prompt_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["is_active"] = bool(item["is_active"])
        return item

    def get_prompt_version(self, agent: str, prompt_version: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT agent,prompt_version,title,description,system_suffix,prompt_family,is_active,created_at,updated_at FROM llm_prompt_version WHERE agent=%s AND prompt_version=%s",
                (agent, prompt_version),
            ).fetchone()
        return self._prompt_dict(row) if row else None

    def list_prompt_versions(self, agent: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT agent,prompt_version,title,description,system_suffix,prompt_family,is_active,created_at,updated_at FROM llm_prompt_version WHERE (%s::text IS NULL OR agent=%s) ORDER BY agent,prompt_version",
                (agent, agent),
            ).fetchall()
        return [self._prompt_dict(row) for row in rows]

    def get_active_prompt_version(self, agent: str, prompt_family: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT agent,prompt_version,title,description,system_suffix,prompt_family,is_active,created_at,updated_at FROM llm_prompt_version WHERE agent=%s AND prompt_family=%s AND is_active=true ORDER BY updated_at DESC LIMIT 1",
                (agent, prompt_family),
            ).fetchone()
        return self._prompt_dict(row) if row else None

    def llm_usage_summary(self, limit: int = 500, agent: str | None = None) -> dict[str, Any]:
        traces = self.list_llm_traces(limit=limit, agent=agent)
        buckets: dict[str, dict[str, dict[str, Any]]] = {
            key: {} for key in ("agent", "model", "prompt")
        }
        total = {"name": "all", "calls": 0, "fallback_calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "latency_ms": 0}

        def add(bucket: dict[str, Any], trace: dict[str, Any]) -> None:
            usage = trace.get("token_usage") if isinstance(trace.get("token_usage"), dict) else {}
            in_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("input_token_count") or 0)
            out_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("output_token_count") or 0)
            all_tokens = int(usage.get("total_tokens") or usage.get("total_token_count") or in_tokens + out_tokens)
            bucket["calls"] += 1
            bucket["fallback_calls"] += int(bool(trace.get("fallback_used")))
            bucket["input_tokens"] += in_tokens
            bucket["output_tokens"] += out_tokens
            bucket["total_tokens"] += all_tokens
            bucket["latency_ms"] += int(trace.get("latency_ms") or 0)

        for trace in traces:
            agent_name = str(trace.get("agent") or "unknown")
            model = str(trace.get("model") or "fallback")
            prompt_key = f"{agent_name}:{trace.get('prompt_version') or 'v1'}"
            add(total, trace)
            for dimension, key in (("agent", agent_name), ("model", model), ("prompt", prompt_key)):
                bucket = buckets[dimension].setdefault(
                    key, {"name": key, "calls": 0, "fallback_calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "latency_ms": 0}
                )
                add(bucket, trace)

        def finalize(bucket: dict[str, Any]) -> dict[str, Any]:
            calls = bucket["calls"]
            return {**bucket, "avg_latency_ms": int(bucket["latency_ms"] / calls) if calls else 0, "fallback_rate": round(bucket["fallback_calls"] / calls, 4) if calls else 0}

        return {
            "total": finalize(total), "by_agent": [finalize(v) for v in buckets["agent"].values()],
            "by_model": [finalize(v) for v in buckets["model"].values()],
            "by_prompt": [finalize(v) for v in buckets["prompt"].values()], "sample_size": len(traces),
        }

    @staticmethod
    def _skill_dict(row: Any) -> dict[str, Any]:
        manifest = row["manifest_json"] or {}
        return {
            **manifest,
            "code": row["skill_id"],
            "source_plugin": manifest.get("source_plugin") or manifest.get("plugin_id"),
            "version": row["version"],
            "enabled": bool(manifest.get("enabled", True)),
        }

    def seed_builtin_skills(self, plugin: dict[str, Any], skills: list[dict[str, Any]]) -> None:
        from app.skills.contract import validate_skill_contract

        now = utc_now_iso()
        plugin_id = str(plugin["plugin_id"])
        with self.connection() as conn:
            old_plugin = conn.execute("SELECT installed_at FROM skill_plugin WHERE plugin_id=%s", (plugin_id,)).fetchone()
            conn.execute(
                """INSERT INTO skill_plugin(plugin_id,name,version,source_type,source_url,author,description,enabled,installed_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(plugin_id) DO UPDATE SET name=EXCLUDED.name,version=EXCLUDED.version,
                   source_type=EXCLUDED.source_type,source_url=EXCLUDED.source_url,author=EXCLUDED.author,
                   description=EXCLUDED.description,enabled=EXCLUDED.enabled,updated_at=EXCLUDED.updated_at""",
                (
                    plugin_id, plugin["name"], plugin.get("version") or "1.0.0",
                    plugin.get("source_type") or "builtin", plugin.get("source_url"), plugin.get("author"),
                    plugin.get("description"), bool(plugin.get("enabled", True)),
                    old_plugin["installed_at"] if old_plugin else now, now,
                ),
            )
            for source_skill in skills:
                contract = source_skill.get("contract") if isinstance(source_skill.get("contract"), dict) else validate_skill_contract(source_skill)
                skill = {
                    **source_skill,
                    "permission_levels": source_skill.get("permission_levels") or contract.get("permission_levels") or [],
                    "risk_level": source_skill.get("risk_level") or contract.get("risk_level") or "low",
                    "contract": contract,
                }
                skill_code = str(skill["code"])
                source_plugin = skill.get("source_plugin") or plugin_id
                version = skill.get("version") or plugin.get("version") or "1.0.0"
                old_skill = conn.execute("SELECT manifest_json,version FROM skill_registry WHERE skill_id=%s FOR UPDATE", (skill_code,)).fetchone()
                if old_skill:
                    skill.setdefault("enabled", bool(old_skill["manifest_json"].get("enabled", True)))
                skill["source_plugin"] = source_plugin
                skill["version"] = version
                conn.execute(
                    """INSERT INTO skill_registry(skill_id,version,manifest_json,approval_status,updated_at)
                       VALUES (%s,%s,%s::jsonb,'approved',%s)
                       ON CONFLICT(skill_id) DO UPDATE SET version=EXCLUDED.version,manifest_json=EXCLUDED.manifest_json,
                       approval_status='approved',updated_at=EXCLUDED.updated_at""",
                    (skill_code, version, json.dumps(skill, ensure_ascii=False), _postgres_timestamp(now)),
                )
                conn.execute(
                    """INSERT INTO skill_approval(skill_code,agent_code,allowed,reason,created_at,updated_at)
                       VALUES (%s,'skill_console',true,'Installed skill approved for console testing.',%s,%s)
                       ON CONFLICT(skill_code,agent_code) DO NOTHING""",
                    (skill_code, now, _postgres_timestamp(now)),
                )
                conn.execute(
                    """INSERT INTO skill_version_snapshot(skill_code,plugin_id,version,snapshot_json,created_at)
                       VALUES (%s,%s,%s,%s::jsonb,%s) ON CONFLICT(skill_code,plugin_id,version)
                       DO UPDATE SET snapshot_json=EXCLUDED.snapshot_json""",
                    (skill_code, source_plugin, version, json.dumps(skill, ensure_ascii=False), now),
                )

    def list_skill_plugins(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM skill_plugin ORDER BY installed_at DESC").fetchall()
        return [{**dict(row), "enabled": bool(row["enabled"])} for row in rows]

    def list_skills(self, category: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT skill_id,version,manifest_json FROM skill_registry WHERE (%s::text IS NULL OR manifest_json->>'category'=%s) ORDER BY manifest_json->>'category',skill_id",
                (category, category),
            ).fetchall()
        return [self._skill_dict(row) for row in rows]

    def get_skill(self, skill_code: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT skill_id,version,manifest_json FROM skill_registry WHERE skill_id=%s", (skill_code,)).fetchone()
        return self._skill_dict(row) if row else None

    def update_skill_enabled(self, skill_code: str, enabled: bool) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE skill_registry SET manifest_json=jsonb_set(manifest_json,'{enabled}',to_jsonb(%s::boolean),true),updated_at=%s WHERE skill_id=%s",
                (enabled, _postgres_timestamp(utc_now_iso()), skill_code),
            )
        return self.get_skill(skill_code)

    def uninstall_skill_plugin(self, plugin_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            plugin = conn.execute("SELECT * FROM skill_plugin WHERE plugin_id=%s FOR UPDATE", (plugin_id,)).fetchone()
            if not plugin:
                return None
            plugin_item = {**dict(plugin), "enabled": bool(plugin["enabled"])}
            if plugin_item["source_type"] == "builtin":
                raise ValueError("Built-in skill plugins cannot be uninstalled.")
            rows = conn.execute(
                "SELECT skill_id FROM skill_registry WHERE manifest_json->>'source_plugin'=%s OR manifest_json->>'plugin_id'=%s",
                (plugin_id, plugin_id),
            ).fetchall()
            skill_codes = [row["skill_id"] for row in rows]
            if skill_codes:
                conn.execute("DELETE FROM skill_approval WHERE skill_code=ANY(%s)", (skill_codes,))
                conn.execute("DELETE FROM skill_registry WHERE skill_id=ANY(%s)", (skill_codes,))
            conn.execute("DELETE FROM skill_plugin WHERE plugin_id=%s", (plugin_id,))
        return {"plugin": plugin_item, "removed_skills": skill_codes, "removed_skill_count": len(skill_codes)}

    def set_skill_approval(self, skill_code: str, agent_code: str, allowed: bool, reason: str | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO skill_approval(skill_code,agent_code,allowed,reason,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(skill_code,agent_code)
                   DO UPDATE SET allowed=EXCLUDED.allowed,reason=EXCLUDED.reason,updated_at=EXCLUDED.updated_at""",
                (skill_code, agent_code, allowed, reason, now, _postgres_timestamp(now)),
            )
        return self.get_skill_approval(skill_code, agent_code) or {}

    def get_skill_approval(self, skill_code: str, agent_code: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT skill_code,agent_code,allowed,reason,created_at,updated_at FROM skill_approval WHERE skill_code=%s AND agent_code=%s", (skill_code, agent_code)).fetchone()
        return {**dict(row), "allowed": bool(row["allowed"])} if row else None

    def list_skill_approvals(self, agent_code: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT skill_code,agent_code,allowed,reason,created_at,updated_at FROM skill_approval WHERE (%s::text IS NULL OR agent_code=%s) ORDER BY updated_at DESC",
                (agent_code, agent_code),
            ).fetchall()
        return [{**dict(row), "allowed": bool(row["allowed"])} for row in rows]

    def save_skill_execution_log(self, log: dict[str, Any]) -> dict[str, Any]:
        created = log.get("created_at") or utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO skill_execution_log(log_id,skill_code,task_id,request_id,actor_id,role,status,
                   latency_ms,error_message,input_json,output_json,created_at,agent_code)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                   ON CONFLICT(log_id) DO UPDATE SET status=EXCLUDED.status,error_message=EXCLUDED.error_message,
                   output_json=EXCLUDED.output_json,latency_ms=EXCLUDED.latency_ms""",
                (
                    log["log_id"], log["skill_code"], log.get("task_id"), log.get("request_id"), log.get("actor_id"),
                    log.get("role"), log.get("status") or "completed", int(log.get("latency_ms") or 0),
                    log.get("error_message"), json.dumps(log.get("input") or {}, ensure_ascii=False),
                    json.dumps(log.get("output") or {}, ensure_ascii=False), _postgres_timestamp(created), log.get("agent_code"),
                ),
            )
        return {**log, "created_at": created, "input": log.get("input") or {}, "output": log.get("output") or {}, "latency_ms": int(log.get("latency_ms") or 0)}

    def list_skill_execution_logs(self, limit: int = 100, skill_code: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT log_id,skill_code,agent_code,task_id,input_json,output_json,status,error_message,latency_ms,request_id,actor_id,role,created_at FROM skill_execution_log WHERE (%s::text IS NULL OR skill_code=%s) ORDER BY created_at DESC LIMIT %s",
                (skill_code, skill_code, max(1, min(limit, 1000))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["input"] = item.pop("input_json") or {}
            item["output"] = item.pop("output_json") or {}
            result.append(item)
        return result

    def list_skill_versions(self, skill_code: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT skill_code,plugin_id,version,snapshot_json,created_at FROM skill_version_snapshot WHERE skill_code=%s ORDER BY id DESC", (skill_code,)).fetchall()
        return [{**{k: v for k, v in dict(row).items() if k != "snapshot_json"}, "snapshot": row["snapshot_json"] or {}} for row in rows]

    def rollback_skill_version(self, skill_code: str, version: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT snapshot_json FROM skill_version_snapshot WHERE skill_code=%s AND version=%s ORDER BY id DESC LIMIT 1", (skill_code, version)).fetchone()
        if not row:
            return None
        snapshot = row["snapshot_json"] or {}
        plugin_id = snapshot.get("source_plugin") or snapshot.get("plugin_id") or "rollback"
        plugin = {"plugin_id": plugin_id, "name": plugin_id, "version": version, "source_type": "rollback", "enabled": True}
        self.seed_builtin_skills(plugin, [{**snapshot, "version": version}])
        return self.get_skill(skill_code)

    def save_marketplace_install(self, record: dict[str, Any]) -> dict[str, Any]:
        installed_at = record.get("installed_at") or utc_now_iso()
        summary, manifest = record.get("summary") or {}, record.get("manifest") or {}
        package_id = str(record.get("package_id") or "").strip()
        if not package_id:
            raise ValueError("package_id is required")
        source = record.get("source") or {"url": record.get("source_url")}
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO plugin_marketplace_install(install_id,package_id,version,source_json,approval_status,
                   approved_by,approved_at,approval_reason,created_at,name,package_type,source_url,status,
                   summary_json,manifest_json,error_message,installed_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                   ON CONFLICT(install_id) DO UPDATE SET version=EXCLUDED.version,source_json=EXCLUDED.source_json,
                   approval_status=EXCLUDED.approval_status,approved_by=EXCLUDED.approved_by,
                   approved_at=EXCLUDED.approved_at,approval_reason=EXCLUDED.approval_reason,
                   name=EXCLUDED.name,package_type=EXCLUDED.package_type,source_url=EXCLUDED.source_url,
                   status=EXCLUDED.status,summary_json=EXCLUDED.summary_json,manifest_json=EXCLUDED.manifest_json,
                   error_message=EXCLUDED.error_message,installed_at=EXCLUDED.installed_at""",
                (
                    record.get("install_id") or f"install_{uuid4().hex}", package_id,
                    str(record.get("version") or "unknown"), json.dumps(source, ensure_ascii=False),
                    record.get("approval_status") or "approved", record.get("approved_by"),
                    _postgres_timestamp(record["approved_at"]) if record.get("approved_at") else None,
                    record.get("approval_reason"), _postgres_timestamp(installed_at),
                    str(record.get("name") or package_id), str(record.get("package_type") or "skill"),
                    record.get("source_url"), record.get("status") or "installed",
                    json.dumps(summary, ensure_ascii=False), json.dumps(manifest, ensure_ascii=False),
                    record.get("error_message"), installed_at,
                ),
            )
        result = {**record, "summary": summary, "manifest": manifest, "installed_at": installed_at, "source": source}
        return result

    @staticmethod
    def _marketplace_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["summary"] = item.pop("summary_json") or {}
        item["manifest"] = item.pop("manifest_json") or {}
        return item

    def list_marketplace_installs(self, limit: int = 80, package_type: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT install_id,package_id,name,package_type,version,source_url,status,summary_json,
                   manifest_json,error_message,approval_status,approved_by,approved_at,approval_reason,installed_at
                   FROM plugin_marketplace_install WHERE (%s::text IS NULL OR package_type=%s)
                   ORDER BY installed_at DESC,created_at DESC LIMIT %s""",
                (package_type, package_type, max(1, min(limit, 1000))),
            ).fetchall()
        return [self._marketplace_dict(row) for row in rows]

    def get_latest_marketplace_install(self, package_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT install_id,package_id,name,package_type,version,source_url,status,summary_json,
                   manifest_json,error_message,approval_status,approved_by,approved_at,approval_reason,installed_at
                   FROM plugin_marketplace_install WHERE package_id=%s ORDER BY installed_at DESC,created_at DESC LIMIT 1""",
                (package_id,),
            ).fetchone()
        return self._marketplace_dict(row) if row else None

    def set_marketplace_approval(
        self, package_id: str, status: str, approved_by: str, reason: str | None = None
    ) -> dict[str, Any] | None:
        if status not in {"approved", "rejected"}:
            raise ValueError("approval status must be approved or rejected")
        with self.connection() as conn:
            row = conn.execute(
                "SELECT install_id FROM plugin_marketplace_install WHERE package_id=%s ORDER BY installed_at DESC,created_at DESC LIMIT 1 FOR UPDATE",
                (package_id,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE plugin_marketplace_install SET approval_status=%s,approved_by=%s,approved_at=%s,approval_reason=%s WHERE install_id=%s",
                (status, approved_by, _postgres_timestamp(utc_now_iso()), reason, row["install_id"]),
            )
        return self.get_latest_marketplace_install(package_id)

    def create_benchmark_run(
        self, run_id: str, name: str, benchmark_type: str,
        config: dict[str, Any], summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _postgres_timestamp(utc_now_iso())
        config_json = json.dumps(config, ensure_ascii=False)
        summary_json = json.dumps(summary or {}, ensure_ascii=False)
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO benchmark_run(run_id,dataset_version,config_json,metrics_json,name,
                   benchmark_type,status,summary_json,started_at,finished_at,created_at)
                   VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,'running',%s::jsonb,%s,NULL,%s)""",
                (
                    run_id, str(config.get("dataset_version") or "unspecified"), config_json,
                    summary_json, name, benchmark_type, summary_json, now, now,
                ),
            )
        return self.get_benchmark_run(run_id) or {}

    def append_benchmark_result(self, result: dict[str, Any]) -> dict[str, Any]:
        result_id = f"bench_result_{uuid4().hex}"
        now = result.get("created_at") or utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO benchmark_result(result_id,run_id,case_id,result_json,server_id,tool_name,
                   iteration,status,latency_ms,error_message,input_json,output_json,created_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
                (
                    result_id, result["run_id"], result["case_id"], json.dumps(result, ensure_ascii=False),
                    result.get("server_id"), result.get("tool_name"), int(result.get("iteration") or 1),
                    result.get("status") or "unknown", int(result.get("latency_ms") or 0),
                    result.get("error_message"), json.dumps(result.get("input") or {}, ensure_ascii=False),
                    json.dumps(result.get("output") or {}, ensure_ascii=False), _postgres_timestamp(now),
                ),
            )
        return {**result, "id": result_id, "created_at": now}

    def finish_benchmark_run(self, run_id: str, status: str, summary: dict[str, Any]) -> dict[str, Any]:
        with self.connection() as conn:
            conn.execute(
                "UPDATE benchmark_run SET status=%s,summary_json=%s::jsonb,metrics_json=%s::jsonb,finished_at=%s WHERE run_id=%s",
                (
                    status, json.dumps(summary, ensure_ascii=False), json.dumps(summary, ensure_ascii=False),
                    _postgres_timestamp(utc_now_iso()), run_id,
                ),
            )
        return self.get_benchmark_run(run_id) or {}

    @staticmethod
    def _benchmark_run_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["config"] = item.pop("config_json") or {}
        item["summary"] = item.pop("summary_json") or {}
        item.setdefault("results", [])
        return item

    @staticmethod
    def _benchmark_result_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["id"] = item.pop("result_id")
        item["input"] = item.pop("input_json") or {}
        item["output"] = item.pop("output_json") or {}
        return item

    def list_benchmark_runs(self, limit: int = 50, benchmark_type: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT run_id,name,benchmark_type,status,config_json,summary_json,started_at,finished_at,created_at
                   FROM benchmark_run WHERE (%s::text IS NULL OR benchmark_type=%s) ORDER BY created_at DESC,run_id DESC LIMIT %s""",
                (benchmark_type, benchmark_type, max(1, min(limit, 500))),
            ).fetchall()
        return [self._benchmark_run_dict(row) for row in rows]

    def get_benchmark_run(self, run_id: str, *, include_results: bool = True) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT run_id,name,benchmark_type,status,config_json,summary_json,started_at,finished_at,created_at FROM benchmark_run WHERE run_id=%s",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            run = self._benchmark_run_dict(row)
            if include_results:
                rows = conn.execute(
                    "SELECT result_id,run_id,case_id,server_id,tool_name,iteration,status,latency_ms,error_message,input_json,output_json,created_at FROM benchmark_result WHERE run_id=%s ORDER BY created_at,result_id",
                    (run_id,),
                ).fetchall()
                run["results"] = [self._benchmark_result_dict(item) for item in rows]
        return run

    def save_mcp_server(self, server: dict[str, Any]) -> dict[str, Any]:
        server_id = str(server.get("server_id") or server.get("name") or "").strip()
        if not server_id:
            raise ValueError("server_id is required")
        now = utc_now_iso()
        with self.connection() as conn:
            old = conn.execute("SELECT created_at FROM mcp_server_config WHERE server_id=%s", (server_id,)).fetchone()
            created_at = old["created_at"] if old and old["created_at"] else now
            conn.execute(
                """INSERT INTO mcp_server_config(
                    server_id,name,transport,command,args_json,env_json,url,enabled,status,last_error,created_at,updated_at
                ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(server_id) DO UPDATE SET name=EXCLUDED.name,transport=EXCLUDED.transport,
                    command=EXCLUDED.command,args_json=EXCLUDED.args_json,env_json=EXCLUDED.env_json,
                    url=EXCLUDED.url,enabled=EXCLUDED.enabled,status=EXCLUDED.status,
                    last_error=EXCLUDED.last_error,updated_at=EXCLUDED.updated_at""",
                (
                    server_id, str(server.get("name") or server_id), str(server.get("transport") or "stdio"),
                    server.get("command") or "", json.dumps(server.get("args") or [], ensure_ascii=False),
                    json.dumps(server.get("env") or {}, ensure_ascii=False), server.get("url"),
                    bool(server.get("enabled")), str(server.get("status") or "unknown"), server.get("last_error"),
                    created_at, _postgres_timestamp(now),
                ),
            )
        return self.get_mcp_server(server_id) or {}

    @staticmethod
    def _mcp_server_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["args"] = item.pop("args_json") or []
        item["env"] = item.pop("env_json") or {}
        item["enabled"] = bool(item["enabled"])
        return item

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT server_id,name,transport,command,args_json,env_json,url,enabled,status,last_error,created_at,updated_at FROM mcp_server_config ORDER BY updated_at DESC"
            ).fetchall()
        return [self._mcp_server_dict(row) for row in rows]

    def get_mcp_server(self, server_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT server_id,name,transport,command,args_json,env_json,url,enabled,status,last_error,created_at,updated_at FROM mcp_server_config WHERE server_id=%s",
                (server_id,),
            ).fetchone()
        return self._mcp_server_dict(row) if row else None

    def update_mcp_server_status(
        self, server_id: str, status: str, last_error: str | None = None, enabled: bool | None = None
    ) -> dict[str, Any] | None:
        with self.connection() as conn:
            if enabled is None:
                conn.execute(
                    "UPDATE mcp_server_config SET status=%s,last_error=%s,updated_at=%s WHERE server_id=%s",
                    (status, last_error, _postgres_timestamp(utc_now_iso()), server_id),
                )
            else:
                conn.execute(
                    "UPDATE mcp_server_config SET status=%s,last_error=%s,enabled=%s,updated_at=%s WHERE server_id=%s",
                    (status, last_error, enabled, _postgres_timestamp(utc_now_iso()), server_id),
                )
        return self.get_mcp_server(server_id)

    def upsert_mcp_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        server_id, name = str(tool.get("server_id") or "").strip(), str(tool.get("name") or "").strip()
        if not server_id or not name:
            raise ValueError("server_id and tool name are required")
        now = utc_now_iso()
        with self.connection() as conn:
            old = conn.execute(
                "SELECT discovered_at FROM mcp_tool_registry WHERE server_id=%s AND tool_name=%s", (server_id, name)
            ).fetchone()
            discovered_at = old["discovered_at"] if old and old["discovered_at"] else now
            conn.execute(
                """INSERT INTO mcp_tool_registry(
                    server_id,tool_name,tool_id,description,input_schema,enabled,status,discovered_at,updated_at
                ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                ON CONFLICT(server_id,tool_name) DO UPDATE SET tool_id=EXCLUDED.tool_id,
                    description=EXCLUDED.description,input_schema=EXCLUDED.input_schema,
                    enabled=EXCLUDED.enabled,status=EXCLUDED.status,updated_at=EXCLUDED.updated_at""",
                (
                    server_id, name, str(tool.get("tool_id") or f"{server_id}:{name}"), tool.get("description"),
                    json.dumps(tool.get("input_schema") or {}, ensure_ascii=False),
                    bool(tool.get("enabled", True)), str(tool.get("status") or "available"), discovered_at,
                    _postgres_timestamp(now),
                ),
            )
        return self.get_mcp_tool(server_id, name) or {}

    def prune_mcp_tools(self, server_id: str, keep_names: set[str]) -> int:
        names = sorted({str(name).strip() for name in keep_names if str(name).strip()})
        with self.connection() as conn:
            if names:
                result = conn.execute(
                    "DELETE FROM mcp_tool_registry WHERE server_id=%s AND NOT (tool_name = ANY(%s))",
                    (server_id, names),
                )
            else:
                result = conn.execute("DELETE FROM mcp_tool_registry WHERE server_id=%s", (server_id,))
        return result.rowcount

    @staticmethod
    def _mcp_tool_dict(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["name"] = item.pop("tool_name")
        item["input_schema"] = item.pop("input_schema") or {}
        item["enabled"] = bool(item["enabled"])
        return item

    def list_mcp_tools(self, server_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT tool_id,server_id,tool_name,description,input_schema,enabled,status,discovered_at,updated_at FROM mcp_tool_registry WHERE (%s::text IS NULL OR server_id=%s) ORDER BY server_id,tool_name",
                (server_id, server_id),
            ).fetchall()
        return [self._mcp_tool_dict(row) for row in rows]

    def get_mcp_tool(self, server_id: str, name: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT tool_id,server_id,tool_name,description,input_schema,enabled,status,discovered_at,updated_at FROM mcp_tool_registry WHERE server_id=%s AND tool_name=%s",
                (server_id, name),
            ).fetchone()
        return self._mcp_tool_dict(row) if row else None

    def update_mcp_tool_enabled(self, server_id: str, name: str, enabled: bool) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE mcp_tool_registry SET enabled=%s,updated_at=%s WHERE server_id=%s AND tool_name=%s",
                (enabled, _postgres_timestamp(utc_now_iso()), server_id, name),
            )
        return self.get_mcp_tool(server_id, name)

    def set_mcp_tool_approval(
        self, agent_code: str, server_id: str, tool_name: str, allowed: bool, reason: str | None = None
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO mcp_tool_approval(agent_code,server_id,tool_name,allowed,reason,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(agent_code,server_id,tool_name) DO UPDATE SET allowed=EXCLUDED.allowed,
                   reason=EXCLUDED.reason,updated_at=EXCLUDED.updated_at""",
                (agent_code, server_id, tool_name, allowed, reason, now, _postgres_timestamp(now)),
            )
        return self.get_mcp_tool_approval(agent_code, server_id, tool_name) or {}

    def get_mcp_tool_approval(self, agent_code: str, server_id: str, tool_name: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT agent_code,server_id,tool_name,allowed,reason,created_at,updated_at FROM mcp_tool_approval WHERE agent_code=%s AND server_id=%s AND tool_name=%s",
                (agent_code, server_id, tool_name),
            ).fetchone()
        return dict(row) if row else None

    def save_mcp_call_log(self, log: dict[str, Any]) -> dict[str, Any]:
        now = log.get("created_at") or utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO mcp_tool_call_log(call_id,request_id,actor_id,role,server_id,tool_name,status,
                    exit_code,latency_ms,error_message,created_at,agent_code,input_json,output_json,command_summary)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                    ON CONFLICT(call_id) DO UPDATE SET status=EXCLUDED.status,exit_code=EXCLUDED.exit_code,
                    latency_ms=EXCLUDED.latency_ms,error_message=EXCLUDED.error_message,
                    output_json=EXCLUDED.output_json""",
                (
                    log["call_id"], log.get("request_id") or "", log.get("actor_id") or "unknown",
                    log.get("role") or "unknown", log.get("server_id") or "", log.get("tool_name") or "",
                    log.get("status") or "unknown", log.get("exit_code"), int(log.get("latency_ms") or 0),
                    log.get("error_message"), _postgres_timestamp(now), log.get("agent_code"),
                    json.dumps(log.get("input") or {}, ensure_ascii=False),
                    json.dumps(log.get("output") or {}, ensure_ascii=False), log.get("command_summary") or "",
                ),
            )
        return {**log, "created_at": now}

    def list_mcp_call_logs(self, limit: int = 100, server_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT call_id,server_id,tool_name,agent_code,input_json,output_json,status,error_message,latency_ms,request_id,actor_id,role,command_summary,exit_code,created_at FROM mcp_tool_call_log WHERE (%s::text IS NULL OR server_id=%s) ORDER BY created_at DESC LIMIT %s",
                (server_id, server_id, max(1, min(limit, 1000))),
            ).fetchall()
        logs = []
        for row in rows:
            item = dict(row)
            item["input"] = item.pop("input_json") or {}
            item["output"] = item.pop("output_json") or {}
            logs.append(item)
        return logs

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

    def claim_task(self, task_id: str, worker_id: str, lease_seconds: int = 30) -> dict[str, Any] | None:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        with self.connection() as conn:
            result = conn.execute(
                "UPDATE agent_task SET status='running',worker_id=%s,lease_until=%s,heartbeat_at=%s,attempt=attempt+1,updated_at=%s WHERE task_id=%s AND status IN ('created','queued')",
                (worker_id, (now + timedelta(seconds=max(1, lease_seconds))).isoformat(), now.isoformat(), now.isoformat(), task_id),
            )
            if result.rowcount != 1:
                return None
            row = conn.execute("SELECT * FROM agent_task WHERE task_id=%s", (task_id,)).fetchone()
        return dict(row) if row else None

    def is_task_cancelled(self, task_id: str) -> bool:
        with self.connection() as conn:
            row = conn.execute("SELECT status FROM agent_task WHERE task_id=%s", (task_id,)).fetchone()
        return bool(row and row["status"] == "cancelled")

    def is_task_failed(self, task_id: str) -> bool:
        with self.connection() as conn:
            row = conn.execute("SELECT status FROM agent_task WHERE task_id=%s", (task_id,)).fetchone()
        return bool(row and row["status"] == "failed")

    def recover_expired_tasks(self) -> int:
        return len(self.recover_expired_task_ids())

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
        actor_id: str = "system-agent",
    ) -> None:
        """Atomically save review, task state, checkpoint and event history."""
        now = utc_now_iso()
        transitions = {
            "created": {"queued", "running", "cancelled", "failed"},
            "queued": {"running", "cancelled", "failed"},
            "running": {"completed", "waiting_review", "paused", "failed", "cancelled", "queued"},
            "waiting_review": {"running", "queued", "completed", "cancelled", "rejected", "paused"},
            "paused": {"queued", "running", "cancelled", "failed"},
            "failed": {"queued", "running"},
            "cancelled": {"queued"},
        }
        with self.connection() as conn:
            row = conn.execute(
                "SELECT status, execution_version, input_json FROM agent_task WHERE task_id=%s FOR UPDATE",
                (task_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Task `{task_id}` does not exist.")
            current_status = str(row["status"])
            if status != current_status and status not in transitions.get(current_status, set()):
                raise ValueError(f"Invalid task status transition: {current_status} -> {status}")
            version = int(row["execution_version"]) + 1
            conn.execute(
                "UPDATE agent_task SET status=%s, updated_at=%s, execution_version=%s, retry_count=retry_count+%s, resume_count=resume_count+%s, input_json=COALESCE(%s::jsonb,input_json), worker_id=CASE WHEN %s THEN NULL ELSE worker_id END, lease_until=CASE WHEN %s THEN NULL ELSE lease_until END, heartbeat_at=CASE WHEN %s THEN NULL ELSE heartbeat_at END WHERE task_id=%s",
                (
                    status, now, version, int(retry), int(resume_input is not None),
                    json.dumps(resume_input, ensure_ascii=False) if resume_input is not None else None,
                    resume_input is not None, resume_input is not None, resume_input is not None, task_id,
                ),
            )
            conn.execute(
                "INSERT INTO human_review_action(review_id,task_id,actor_id,action,payload_json,created_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    f"review_{uuid4().hex}", task_id, actor_id, action,
                    json.dumps({"comment": comment}, ensure_ascii=False), now,
                ),
            )
            if checkpoint is not None:
                conn.execute(
                    "INSERT INTO agent_task_artifact(task_id,artifact_type,name,content_json,execution_version,created_at) VALUES (%s,'workflow_checkpoint','review',%s::jsonb,%s,%s)",
                    (task_id, json.dumps(checkpoint, ensure_ascii=False), version, now),
                )
            seq = conn.execute(
                "SELECT COALESCE(MAX(event_seq),0)+1 AS seq FROM agent_task_event WHERE task_id=%s",
                (task_id,),
            ).fetchone()["seq"]
            for event in events:
                event_id = event.get("event_id") or f"evt_{uuid4().hex}"
                conn.execute(
                    "INSERT INTO agent_task_event(event_id,task_id,event_type,node,agent,status,content,data_json,event_seq,execution_version,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT(event_id) DO NOTHING",
                    (
                        event_id, task_id, event.get("type", "human_review"), event.get("node"),
                        event.get("agent", "human_reviewer"), event.get("status", status),
                        event.get("content"), json.dumps(event.get("data", {}), ensure_ascii=False),
                        seq, version, event.get("timestamp") or now,
                    ),
                )
                seq += 1

    def queue_task_resume(
        self, task_id: str, checkpoint: dict[str, Any], action: str, comment: str | None,
    ) -> None:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task `{task_id}` does not exist.")
        if task["status"] != "waiting_review":
            raise ValueError(f"Task `{task_id}` is not waiting for review.")
        task_input = self.get_task_input(task_id)
        task_input["_jaycode_runner"] = "resume"
        task_input["_resume_payload"] = {"checkpoint": checkpoint, "action": action, "comment": comment}
        self.apply_review_transition(
            task_id, action, comment, "queued",
            [{
                "event_id": f"evt_{uuid4().hex}", "type": "human_review",
                "node": str(checkpoint.get("paused_node_id") or "human_review"),
                "status": "queued", "content": f"Review action {action} queued for resume.",
                "data": {"action": action, "resume": True},
            }],
            checkpoint=checkpoint,
            resume_input=task_input,
        )

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
