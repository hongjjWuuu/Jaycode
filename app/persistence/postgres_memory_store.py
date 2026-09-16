"""PostgreSQL implementation of governed memory persistence."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from app.harness.events import utc_now_iso


class PostgresMemoryStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL memory persistence")
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("psycopg is required for PostgreSQL persistence") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=10)

    def _legacy_init_schema(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS memory_record (
                memory_id TEXT PRIMARY KEY, actor_id TEXT, scope TEXT NOT NULL, scope_id TEXT NOT NULL,
                memory_type TEXT NOT NULL, memory_key TEXT NOT NULL, content TEXT NOT NULL,
                content_hash TEXT NOT NULL, confidence DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL, source_type TEXT NOT NULL, source_ref TEXT,
                source_task_id TEXT, confirmed_by TEXT, superseded_by TEXT, revoked_at TEXT,
                extraction_source TEXT NOT NULL DEFAULT 'rule_fallback',
                quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                quality_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
                retention_policy TEXT NOT NULL DEFAULT 'review_90d', expires_at TEXT,
                conflict_with TEXT, rag_path TEXT, content_json JSONB, source_json JSONB,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, confirmed_at TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS memory_lifecycle_event (
                event_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, action TEXT NOT NULL,
                actor_id TEXT, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_record(scope, scope_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_memory_hash ON memory_record(scope, scope_id, content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_memory_lifecycle_memory ON memory_lifecycle_event(memory_id, created_at)",
        )
        with self._connect() as conn:
            for statement in statements:
                conn.execute(statement)

    def init_schema(self) -> None:
        """Use the single versioned PostgreSQL schema migration entry point."""
        from app.persistence.postgres_store import PostgresTaskStore

        PostgresTaskStore(self.database_url).init_full_schema()

    def extract_candidates(
        self,
        text: str,
        *,
        scope: str = "user",
        scope_id: str = "local-user",
        source_type: str = "conversation",
        source_ref: str | None = None,
        source_task_id: str | None = None,
        actor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        from app.persistence.memory_store import _extract_memory_candidates, _memory_governance

        if scope not in {"user", "project", "team"}:
            raise ValueError("scope must be user, project, or team")
        candidates, extraction_source = _extract_memory_candidates(text)
        created: list[dict[str, Any]] = []
        now = utc_now_iso()
        with self._connect() as conn:
            for candidate in candidates:
                content_hash = hashlib.sha256(candidate["content"].encode("utf-8")).hexdigest()
                duplicate = conn.execute(
                    "SELECT * FROM memory_record WHERE scope=%s AND scope_id=%s AND content_hash=%s AND status!='rejected'",
                    (scope, scope_id, content_hash),
                ).fetchone()
                if duplicate:
                    row = dict(duplicate)
                    row["duplicate"] = True
                    created.append(row)
                    continue
                conflict = conn.execute(
                    "SELECT memory_id FROM memory_record WHERE scope=%s AND scope_id=%s AND memory_key=%s AND status='confirmed' AND content_hash!=%s ORDER BY updated_at DESC LIMIT 1",
                    (scope, scope_id, candidate["memory_key"], content_hash),
                ).fetchone()
                governance = _memory_governance(candidate, extraction_source)
                record = {
                    "memory_id": f"mem_{uuid4().hex}", "scope": scope, "scope_id": scope_id,
                    "memory_type": candidate["memory_type"], "memory_key": candidate["memory_key"],
                    "content": candidate["content"], "content_hash": content_hash,
                    "confidence": candidate["confidence"], "status": "candidate",
                    "source_type": source_type, "source_ref": source_ref,
                    "source_task_id": source_task_id, "confirmed_by": None,
                    "superseded_by": None, "revoked_at": None,
                    "extraction_source": extraction_source, **governance,
                    "conflict_with": conflict["memory_id"] if conflict else None,
                    "rag_path": None, "created_at": now, "updated_at": now,
                    "confirmed_at": None, "duplicate": False,
                }
                conn.execute(
                    """INSERT INTO memory_record(
                        memory_id,actor_id,scope,scope_id,memory_type,memory_key,content,content_json,source_json,content_hash,confidence,
                        status,source_type,source_ref,source_task_id,confirmed_by,superseded_by,revoked_at,
                        extraction_source,quality_score,quality_reasons,retention_policy,expires_at,
                        conflict_with,rag_path,created_at,updated_at,confirmed_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        record["memory_id"], actor_id or scope_id, scope, scope_id, record["memory_type"], record["memory_key"],
                        record["content"], json.dumps({"text": record["content"]}, ensure_ascii=False),
                        json.dumps({"type": source_type, "ref": source_ref, "task_id": source_task_id}, ensure_ascii=False),
                        content_hash, record["confidence"], record["status"], source_type,
                        source_ref, source_task_id, None, None, None, extraction_source,
                        record["quality_score"], json.dumps(record["quality_reasons"], ensure_ascii=False),
                        record["retention_policy"], record["expires_at"], record["conflict_with"], None,
                        now, now, None,
                    ),
                )
                self._audit(conn, record["memory_id"], "created", actor_id, {"source_type": source_type, "source_ref": source_ref})
                created.append(record)
        return created

    def _audit(self, conn: Any, memory_id: str, action: str, actor_id: str | None, metadata: dict[str, Any]) -> None:
        from datetime import datetime

        from app.harness.events import BEIJING_TZ

        conn.execute(
            "INSERT INTO memory_lifecycle_event(event_id,memory_id,action,actor_id,metadata_json,created_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
            (
                f"mem_evt_{uuid4().hex}", memory_id, action, actor_id or "system-agent",
                json.dumps(metadata, ensure_ascii=False),
                datetime.now(BEIJING_TZ).isoformat(timespec="microseconds"),
            ),
        )

    @staticmethod
    def _row(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        reasons = result.get("quality_reasons")
        if isinstance(reasons, (list, dict)):
            result["quality_reasons"] = json.dumps(reasons, ensure_ascii=False)
        return result

    def expire_due_memories(self) -> int:
        from datetime import datetime

        from app.harness.events import BEIJING_TZ
        from app.persistence.memory_store import _is_due

        now = utc_now_iso()
        with self._connect() as conn:
            candidates = conn.execute(
                "SELECT memory_id,expires_at FROM memory_record WHERE status IN ('candidate','confirmed') AND expires_at IS NOT NULL"
            ).fetchall()
            due = [str(row["memory_id"]) for row in candidates if _is_due(row["expires_at"], datetime.now(BEIJING_TZ))]
            for memory_id in due:
                conn.execute("UPDATE memory_record SET status='expired',updated_at=%s WHERE memory_id=%s", (now, memory_id))
                self._audit(conn, memory_id, "expired", None, {})
        return len(due)

    def list_memories(self, *, scope: str | None = None, scope_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        self.expire_due_memories()
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in (("scope", scope), ("scope_id", scope_id), ("status", status)):
            if value:
                clauses.append(f"{column}=%s")
                values.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM memory_record {where} ORDER BY updated_at DESC", values).fetchall()
        return [self._row(row) or {} for row in rows]

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        self.expire_due_memories()
        with self._connect() as conn:
            return self._row(conn.execute("SELECT * FROM memory_record WHERE memory_id=%s", (memory_id,)).fetchone())

    def confirm(self, memory_id: str, rag_path: str, actor_id: str | None = None) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as conn:
            memory = conn.execute("SELECT * FROM memory_record WHERE memory_id=%s FOR UPDATE", (memory_id,)).fetchone()
            if not memory:
                return None
            old_id = memory["conflict_with"]
            if old_id:
                conn.execute("UPDATE memory_record SET status='superseded',superseded_by=%s,updated_at=%s WHERE memory_id=%s", (memory_id, now, old_id))
                self._audit(conn, old_id, "superseded", actor_id, {"superseded_by": memory_id})
            conn.execute("UPDATE memory_record SET status='confirmed',rag_path=%s,confirmed_at=%s,confirmed_by=%s,updated_at=%s WHERE memory_id=%s", (rag_path, now, actor_id, now, memory_id))
            self._audit(conn, memory_id, "confirmed", actor_id, {"rag_path": rag_path})
        return self.get_memory(memory_id)

    def reject(self, memory_id: str, actor_id: str | None = None) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute("UPDATE memory_record SET status='rejected',updated_at=%s WHERE memory_id=%s RETURNING memory_id", (now, memory_id)).fetchone()
            if row:
                self._audit(conn, memory_id, "rejected", actor_id, {})
        return self.get_memory(memory_id) if row else None

    def delete(self, memory_id: str, actor_id: str | None = None) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT memory_id FROM memory_record WHERE memory_id=%s FOR UPDATE", (memory_id,)).fetchone()
            if not row:
                return False
            self._audit(conn, memory_id, "deleted", actor_id, {})
            conn.execute("DELETE FROM memory_record WHERE memory_id=%s", (memory_id,))
            return True

    def list_lifecycle_events(self, memory_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory_lifecycle_event WHERE memory_id=%s ORDER BY created_at,event_id", (memory_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            metadata = item.pop("metadata_json", {})
            item["metadata"] = metadata if isinstance(metadata, dict) else json.loads(metadata or "{}")
            result.append(item)
        return result
