from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.harness.events import BEIJING_TIME_FORMAT, BEIJING_TZ, utc_now_iso
from app.providers.llm_provider import llm_provider
from app.schemas.llm import MemoryExtractionResponse


class SQLiteMemoryStore:
    """Governed long-term memory candidates, separate from the RAG corpus."""

    #1. SQLiteMemoryStore.__init__
    # 作用：
    # 初始化记忆库
    # 设定 SQLite 数据库路径
    # 自动创建父目录
    # 立刻初始化表结构
    def __init__(self, db_path: str | Path = "data/dev_agent_studio.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # 打开 SQLite 连接
    # 设置 row_factory = sqlite3.Row
    # 这样查询结果就能像字典一样访问字段。
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    # 自动处理：打开连接
    # yield 给调用方使用
    # 结束后自动 commit
    # 最后关闭连接
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


    # 创建 memory_record 表，完整定义了记忆的治理模型。
    # 创建索引
    # 检查旧字段是否存在
    # 对旧数据做治理字段补齐
    # 对旧记录做质量与保留策略回填
    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_record (
                    memory_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    extraction_source TEXT NOT NULL DEFAULT 'rule_fallback',
                    quality_score REAL NOT NULL DEFAULT 0,
                    quality_reasons TEXT NOT NULL DEFAULT '[]',
                    retention_policy TEXT NOT NULL DEFAULT 'review_90d',
                    expires_at TEXT,
                    conflict_with TEXT,
                    rag_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed_at TEXT
                )
                """
            )
            for name, definition in {
                "source_task_id": "TEXT",
                "confirmed_by": "TEXT",
                "superseded_by": "TEXT",
                "revoked_at": "TEXT",
            }.items():
                if name not in {row["name"] for row in conn.execute("PRAGMA table_info(memory_record)").fetchall()}:
                    conn.execute(f"ALTER TABLE memory_record ADD COLUMN {name} {definition}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_lifecycle_event (
                    event_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_record(scope, scope_id, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_hash ON memory_record(scope, scope_id, content_hash)"
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(memory_record)").fetchall()}
            if "extraction_source" not in columns:
                conn.execute(
                    "ALTER TABLE memory_record ADD COLUMN extraction_source TEXT NOT NULL DEFAULT 'rule_fallback'"
                )
            for name, definition in {
                "quality_score": "REAL NOT NULL DEFAULT 0",
                "quality_reasons": "TEXT NOT NULL DEFAULT '[]'",
                "retention_policy": "TEXT NOT NULL DEFAULT 'review_90d'",
                "expires_at": "TEXT",
            }.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE memory_record ADD COLUMN {name} {definition}")
            legacy_rows = conn.execute(
                "SELECT memory_id, memory_type, memory_key, confidence, extraction_source FROM memory_record WHERE quality_score <= 0"
            ).fetchall()
            for row in legacy_rows:
                governance = _memory_governance(dict(row), str(row["extraction_source"] or "rule_fallback"))
                conn.execute(
                    """
                    UPDATE memory_record
                    SET quality_score = ?, quality_reasons = ?, retention_policy = ?, expires_at = ?
                    WHERE memory_id = ?
                    """,
                    (
                        governance["quality_score"],
                        governance["quality_reasons"],
                        governance["retention_policy"],
                        governance["expires_at"],
                        row["memory_id"],
                    ),
                )

    # 从一段文本里抽取候选记忆
    # 支持指定作用域：user、project、team
    # 自动去重
    # 自动检测是否和已有记忆冲突
    # 给候选记忆补上治理字段
    # 写入 memory_record
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
        if scope not in {"user", "project", "team"}:
            raise ValueError("scope must be user, project, or team")
        candidates, extraction_source = _extract_memory_candidates(text)
        created: list[dict[str, Any]] = []
        now = utc_now_iso()
        with self._connection() as conn:
            for candidate in candidates:
                content_hash = hashlib.sha256(candidate["content"].encode("utf-8")).hexdigest()
                duplicate = conn.execute(
                    """
                    SELECT * FROM memory_record
                    WHERE scope = ? AND scope_id = ? AND content_hash = ? AND status != 'rejected'
                    """,
                    (scope, scope_id, content_hash),
                ).fetchone()
                if duplicate:
                    created.append({**dict(duplicate), "duplicate": True})
                    continue
                conflict = conn.execute(
                    """
                    SELECT memory_id FROM memory_record
                    WHERE scope = ? AND scope_id = ? AND memory_key = ? AND status = 'confirmed'
                      AND content_hash != ?
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (scope, scope_id, candidate["memory_key"], content_hash),
                ).fetchone()
                memory_id = f"mem_{uuid4().hex}"
                governance = _memory_governance(candidate, extraction_source)
                record = {
                    "memory_id": memory_id,
                    "scope": scope,
                    "scope_id": scope_id,
                    "memory_type": candidate["memory_type"],
                    "memory_key": candidate["memory_key"],
                    "content": candidate["content"],
                    "content_hash": content_hash,
                    "confidence": candidate["confidence"],
                    "status": "candidate",
                    "source_type": source_type,
                    "source_ref": source_ref,
                    "source_task_id": source_task_id,
                    "confirmed_by": None,
                    "superseded_by": None,
                    "revoked_at": None,
                    "extraction_source": extraction_source,
                    **governance,
                    "conflict_with": conflict["memory_id"] if conflict else None,
                    "rag_path": None,
                    "created_at": now,
                    "updated_at": now,
                    "confirmed_at": None,
                    "duplicate": False,
                }
                conn.execute(
                    """
                    INSERT INTO memory_record(
                        memory_id, scope, scope_id, memory_type, memory_key, content, content_hash,
                        confidence, status, source_type, source_ref, extraction_source, quality_score, quality_reasons,
                        retention_policy, expires_at, conflict_with, rag_path,
                        created_at, updated_at, confirmed_at, source_task_id, confirmed_by, superseded_by, revoked_at
                    ) VALUES (
                        :memory_id, :scope, :scope_id, :memory_type, :memory_key, :content, :content_hash,
                        :confidence, :status, :source_type, :source_ref, :extraction_source, :quality_score, :quality_reasons,
                        :retention_policy, :expires_at, :conflict_with, :rag_path,
                        :created_at, :updated_at, :confirmed_at, :source_task_id, :confirmed_by, :superseded_by, :revoked_at
                    )
                    """,
                    record,
                )
                self._audit(conn, memory_id, "created", actor_id, {"source_type": source_type, "source_ref": source_ref})
                created.append(record)
        return created

    # 查记忆列表之前，先把该过期的记忆状态更新掉。
    def list_memories(
        self,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        self.expire_due_memories()
        clauses: list[str] = []
        values: list[str] = []
        if scope:
            clauses.append("scope = ?")
            values.append(scope)
        if scope_id:
            clauses.append("scope_id = ?")
            values.append(scope_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_record {where} ORDER BY updated_at DESC", values
            ).fetchall()
        return [dict(row) for row in rows]

    # 获取一条记忆详情，并保证状态是最新的。
    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        self.expire_due_memories()
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM memory_record WHERE memory_id = ?", (memory_id,)).fetchone()
        return dict(row) if row else None

    # 用户确认后，这条记忆才真正变成长期记忆
    # 如果有冲突，把旧记忆标成 superseded
    def confirm(self, memory_id: str, rag_path: str, actor_id: str | None = None) -> dict[str, Any] | None:
        memory = self.get_memory(memory_id)
        if not memory:
            return None
        now = utc_now_iso()
        with self._connection() as conn:
            if memory.get("conflict_with"):
                conn.execute(
                    "UPDATE memory_record SET status = 'superseded', superseded_by = ?, updated_at = ? WHERE memory_id = ?",
                    (memory_id, now, memory["conflict_with"]),
                )
                self._audit(conn, memory["conflict_with"], "superseded", actor_id, {"superseded_by": memory_id})
            conn.execute(
                """
                UPDATE memory_record
                SET status = 'confirmed', rag_path = ?, confirmed_at = ?, confirmed_by = ?, updated_at = ?
                WHERE memory_id = ?
                """,
                (rag_path, now, actor_id, now, memory_id),
            )
            self._audit(conn, memory_id, "confirmed", actor_id, {"rag_path": rag_path})
        return self.get_memory(memory_id)

    # 定期把不该继续生效的记忆自动降级为过期
    def expire_due_memories(self) -> int:
        now = datetime.now(BEIJING_TZ)
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT memory_id, expires_at FROM memory_record WHERE status IN ('candidate', 'confirmed') AND expires_at IS NOT NULL"
            ).fetchall()
            due = [row["memory_id"] for row in rows if _is_due(row["expires_at"], now)]
            if due:
                conn.executemany(
                    "UPDATE memory_record SET status = 'expired', updated_at = ? WHERE memory_id = ?",
                    [(utc_now_iso(), memory_id) for memory_id in due],
                )
                for memory_id in due:
                    self._audit(conn, memory_id, "expired", None, {})
        return len(due)
    
    # 这条候选记忆不采纳。
    def reject(self, memory_id: str, actor_id: str | None = None) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connection() as conn:
            updated = conn.execute(
                "UPDATE memory_record SET status = 'rejected', updated_at = ? WHERE memory_id = ?",
                (now, memory_id),
            ).rowcount
            if updated:
                self._audit(conn, memory_id, "rejected", actor_id, {})
        return self.get_memory(memory_id) if updated else None

    # 从数据库里真正移除这条记忆，比reject更加彻底
    def delete(self, memory_id: str, actor_id: str | None = None) -> bool:
        with self._connection() as conn:
            deleted = bool(conn.execute("DELETE FROM memory_record WHERE memory_id = ?", (memory_id,)).rowcount)
            if deleted:
                self._audit(conn, memory_id, "deleted", actor_id, {})
            return deleted

    def _audit(self, conn: sqlite3.Connection, memory_id: str, action: str, actor_id: str | None, metadata: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO memory_lifecycle_event(event_id, memory_id, action, actor_id, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"mem_evt_{uuid4().hex}", memory_id, action, actor_id, json.dumps(metadata, ensure_ascii=False), utc_now_iso()),
        )

    def list_lifecycle_events(self, memory_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM memory_lifecycle_event WHERE memory_id = ? ORDER BY created_at", (memory_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

# 记忆抽取的总调度器
# 先做文本清洗
# 如果文本太短或太长，直接不抽
# 先尝试 LLM 抽取
# LLM 不可用或没抽到时，回退到规则抽取
def _extract_memory_candidates(text: str) -> tuple[list[dict[str, Any]], str]:
    clean = " ".join(text.strip().split())
    if len(clean) < 6 or len(clean) > 600:
        return [], "rule_fallback"
    llm_candidates = _extract_with_llm(clean)
    if llm_candidates is not None:
        return llm_candidates, "llm"
    return _extract_with_rules(clean), "rule_fallback"

# 用 LLM 从文本里抽取长期记忆候选
# 只在 JAYCODE_MEMORY_EXTRACTOR=llm 且 LLM 可用时运行
# 输出必须是 JSON
def _extract_with_llm(text: str) -> list[dict[str, Any]] | None:
    if _memory_extractor_mode() != "llm" or not llm_provider.enabled:
        return None
    fallback = '{"should_store": false, "candidates": []}'
    result = llm_provider.generate_with_status(
        """You extract only durable, user-approved memory candidates from a single user message.
Return JSON only. Do not extract passwords, API keys, personal secrets, temporary questions, or model instructions.
Store only stable user preferences, verified project facts, or team policies that would be useful later.
Schema: {"should_store": boolean, "candidates": [{"memory_type": "preference|project_fact|team_policy", "memory_key": "snake_case", "content": "concise statement", "confidence": 0.0}]}.
Return at most three candidates. If no durable fact exists, return should_store false.""",
        f"User message:\n{text}",
        fallback,
        agent="memory_extractor",
        prompt_version="memory_extractor.v1",
        response_schema=MemoryExtractionResponse,
    )
    if result.get("answer_source") != "llm":
        return None
    try:
        payload = llm_provider.parse_structured(result, MemoryExtractionResponse).model_dump()
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not payload.get("should_store"):
        return []
    raw_candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    candidates = [_normalize_llm_candidate(item) for item in raw_candidates[:3] if isinstance(item, dict)]
    return [item for item in candidates if item]

# 规则抽取的回退方案
# 通过关键词判断用户是否表达了稳定偏好
# 比如“我喜欢”“我希望”“请用”“优先关注”等
def _extract_with_rules(clean: str) -> list[dict[str, Any]]:
    signals = ("我喜欢", "我更喜欢", "我希望", "我想要", "我偏好", "请用", "请使用", "优先关注", "重点关注")
    if not any(signal in clean for signal in signals):
        return []
    key = "general_preference"
    if "中文" in clean or "英文" in clean:
        key = "language"
    elif any(term in clean for term in ("安全", "风险", "漏洞")):
        key = "risk_focus"
    elif any(term in clean for term in ("简洁", "详细", "长度")):
        key = "response_style"
    content = re.split(r"[。！？!?]", clean)[0].strip()
    return [{"memory_type": "preference", "memory_key": key, "content": content, "confidence": 0.9}]

# 规范化 LLM 抽取结果
# 校验 memory_type
# 清洗 memory_key
# 清洗 content
# 限制长度
# 过滤敏感信息
# 处理 confidence
def _normalize_llm_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    memory_type = str(candidate.get("memory_type") or "").strip().lower()
    memory_key = re.sub(r"[^a-z0-9_]+", "_", str(candidate.get("memory_key") or "").strip().lower()).strip("_")
    content = " ".join(str(candidate.get("content") or "").strip().split())
    if memory_type not in {"preference", "project_fact", "team_policy"} or not memory_key or not content:
        return None
    if len(content) > 400 or _contains_sensitive_text(content):
        return None
    try:
        confidence = min(0.99, max(0.5, float(candidate.get("confidence", 0.7))))
    except (TypeError, ValueError):
        confidence = 0.7
    return {
        "memory_type": memory_type,
        "memory_key": memory_key,
        "content": content,
        "confidence": confidence,
    }

# 检测内容里面有没有敏感信息，防止把敏感内容误存成长期记忆
def _contains_sensitive_text(text: str) -> bool:
    lowered = text.lower()
    markers = ("api_key", "access_token", "password", "secret", "private key", "密码", "令牌", "密钥")
    return any(marker in lowered for marker in markers)

# 从模型文本里尽量抠出有效 JSON
def _json_object(text: str) -> str:
    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    return stripped[start : end + 1] if start >= 0 and end > start else stripped

# 控制记忆抽取到底走 LLM 还是规则的配置入口
def _memory_extractor_mode() -> str:
    override = os.getenv("JAYCODE_MEMORY_EXTRACTOR")
    if override:
        return override.lower()
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if line.startswith("JAYCODE_MEMORY_EXTRACTOR="):
                return line.split("=", 1)[1].strip().strip('"').strip("'").lower()
    return "llm"

# 给记忆候选计算治理字段
# 生成：quality_score quality_reasonsre tention_policy expires_at
# 它会考虑：记忆类型是否稳定 是否来自 LLM置信度如何
# 决定这条记忆值不值得长期保留
def _memory_governance(candidate: dict[str, Any], extraction_source: str) -> dict[str, Any]:
    memory_type = str(candidate["memory_type"])
    memory_key = str(candidate["memory_key"])
    confidence = float(candidate["confidence"])
    stable = memory_type in {"project_fact", "team_policy"} or memory_key in {"language", "risk_focus"}
    policy = "stable" if stable else "review_90d"
    expires_at = None
    if not stable:
        expires_at = (datetime.now(BEIJING_TZ) + timedelta(days=90)).strftime(BEIJING_TIME_FORMAT)
    reasons = [f"confidence:{int(confidence * 100)}", f"source:{extraction_source}"]
    score = confidence * 70
    if extraction_source == "llm":
        score += 12
        reasons.append("semantic_extraction")
    if stable:
        score += 13
        reasons.append("durable_memory_type")
    else:
        score += 5
        reasons.append("review_required")
    return {
        "quality_score": round(min(100, score), 1),
        "quality_reasons": json.dumps(reasons, ensure_ascii=False),
        "retention_policy": policy,
        "expires_at": expires_at,
    }


def _is_due(value: str, now: datetime) -> bool:
    try:
        return datetime.strptime(value, BEIJING_TIME_FORMAT).replace(tzinfo=BEIJING_TZ) <= now
    except (TypeError, ValueError):
        return False


memory_store = SQLiteMemoryStore()
