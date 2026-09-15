from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.harness.events import utc_now_iso
from app.providers.llm_provider import llm_provider
from app.schemas.llm import RerankResponse


class SQLiteRagStore:
    def __init__(self, db_path: str | Path = "data/dev_agent_studio.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # 连接管理
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # 让查询结果可以用 row["字段名"] 访问
        return conn

    # 在 with self._connection() as conn: 
    # 自动处理提交和关闭，防止连接泄漏。
    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn # 把连接交给调用方
            conn.commit()  # 自动提交
        finally:
            conn.close()  # 自动关闭

    # 建表
    def _init_schema(self) -> None:
        with self._connection() as conn:
            # 建基础表
            # 文档表：存文件的元信息
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_document (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 切片表：存文档切成的片段
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL 
                )
                """
            )

            # 查已有字段
            document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rag_document)").fetchall()}
            # 缺什么加什么
            # 逐个检查 5 个新字段，如果表里没有就加。
            # 从旧版本升级：旧数据保留，新字段用 DEFAULT 值填充
            for name, definition in {
                "content_hash": "TEXT",
                "version": "INTEGER NOT NULL DEFAULT 1",
                "is_current": "INTEGER NOT NULL DEFAULT 1",
                "valid_to": "TEXT",
                "acl_json": "TEXT NOT NULL DEFAULT '[\"*\"]'",
            }.items():
                if name not in document_columns:
                    conn.execute(f"ALTER TABLE rag_document ADD COLUMN {name} {definition}")
            
            # 关联文档的版本
            chunk_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rag_chunk)").fetchall()}
            if "document_version" not in chunk_columns:
                conn.execute("ALTER TABLE rag_chunk ADD COLUMN document_version INTEGER NOT NULL DEFAULT 1")
            if "metadata_json" not in chunk_columns:
                conn.execute("ALTER TABLE rag_chunk ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_document_current ON rag_document(collection, path, is_current)")
            
            # 评测数据集表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_gold_case (
                    case_id TEXT PRIMARY KEY,
                    collection TEXT NOT NULL,
                    question TEXT NOT NULL,
                    expected_chunk_ids_json TEXT NOT NULL,  
                    expected_paths_json TEXT NOT NULL,
                    expected_keywords_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
    
    # 增量索引 + 版本管理
    # RAG 不是每次全量重建，而是增量治理
    def ingest(self, collection: str, documents: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> dict[str, int]:
        grouped = _group_chunks(chunks) # 按文档路径分组
        changed_documents = 0
        with self._connection() as conn:
            for doc in documents:
                path = str(doc["path"])
                content_hash = _content_hash(grouped.get(path, [])) # 计算新内容的 hash
                
                # 查当前版本
                existing = conn.execute(
                    "SELECT id, content_hash, version, acl_json FROM rag_document WHERE collection = ? AND path = ? AND is_current = 1 ORDER BY version DESC LIMIT 1",
                    (collection, path),
                ).fetchone()

                 # 内容没变 → 跳过
                if existing and existing["content_hash"] == content_hash:
                    continue

                # 内容变了 → 版本 +1
                changed_documents += 1
                version = int(existing["version"] or 0) + 1 if existing else 1
                 
                # 保留权限设置
                acl_json = existing["acl_json"] if existing else '["*"]'
                # 旧版本标记为非当前
                if existing:
                    conn.execute("UPDATE rag_document SET is_current = 0, valid_to = ? WHERE id = ?", (utc_now_iso(), existing["id"]))
                # 新版本入库
                conn.execute(
                    "INSERT INTO rag_document(collection, path, size, created_at, content_hash, version, is_current, acl_json) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                    (collection, path, doc.get("size"), utc_now_iso(), content_hash, version, acl_json),
                )
                # 删除旧切片，插入新切片
                conn.execute("DELETE FROM rag_chunk WHERE collection = ? AND path = ? AND document_version = ?", (collection, path, version))
                for chunk in grouped.get(path, []):
                    conn.execute(
                        "INSERT INTO rag_chunk(collection, chunk_id, path, content, metadata_json, created_at, document_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (collection, chunk["chunk_id"], path, chunk["content"], json.dumps(chunk.get("metadata") or {}, ensure_ascii=False), utc_now_iso(), version),
                    )
        return {"document_count": len(documents), "chunk_count": len(chunks), "changed_document_count": changed_documents}

    # 混合检索（query）
    def query(self, collection: str, question: str, limit: int = 5, actor_id: str = "local-user") -> list[dict[str, Any]]:
        
        # 第一步：查出所有当前版本的切片
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT c.chunk_id, c.path, c.content, c.metadata_json, d.acl_json
                FROM rag_chunk c JOIN rag_document d
                  ON c.collection = d.collection AND c.path = d.path AND c.document_version = d.version
                WHERE c.collection = ? AND d.is_current = 1
                """,
                (collection,),
            ).fetchall()
        # 第二步：ACL 过滤 
        visible = [
            {"chunk_id": row["chunk_id"], "path": row["path"], "content": row["content"], "metadata": json.loads(row["metadata_json"] or "{}")}
            for row in rows
            if _acl_allows(row["acl_json"], actor_id)
        ]
        # 第三步：混合排序
        ranked = _rank_hybrid(question, visible)
        # 第四步：可选 LLM 重排
        reranked = _rerank_candidates(question, ranked[: max(limit * 4, 20)])
         # 第五步：返回 top N
        return [_public_rag_result(item) for item in reranked[:limit]]

    # 列出所有文档（带 ACL 过滤）
    def list_documents(self, collection: str | None = None, actor_id: str = "local-user") -> list[dict[str, Any]]:
        with self._connection() as conn:
            if collection:
                rows = conn.execute(
                    "SELECT collection, path, size, created_at, version, is_current, valid_to, acl_json FROM rag_document WHERE collection = ? ORDER BY path, version DESC",
                    (collection,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT collection, path, size, created_at, version, is_current, valid_to, acl_json FROM rag_document ORDER BY collection, path, version DESC"
                ).fetchall()
        return [{key: value for key, value in dict(row).items() if key != "acl_json"} for row in rows if _acl_allows(row["acl_json"], actor_id)]

    # 给文档设置访问控制
    def set_document_acl(self, collection: str, path: str, principals: list[str]) -> bool:
        with self._connection() as conn:
            # 设置文档权限
            updated = conn.execute(
                "UPDATE rag_document SET acl_json = ? WHERE collection = ? AND path = ? AND is_current = 1",
                (json.dumps(sorted(set(principals or ["*"]))), collection, path),
            ).rowcount
        return bool(updated)

    # 列出评测用例
    def list_gold_cases(self, collection: str | None = None, include_disabled: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM rag_gold_case"
        params: list[Any] = []
        clauses: list[str] = []
        if collection:
            clauses.append("collection = ?")
            params.append(collection)
        if not include_disabled:
            clauses.append("enabled = 1")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC"
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_gold_row_to_dict(dict(row)) for row in rows]

    # 保存评测用例
    def save_gold_case(self, case: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        case_id = str(case.get("case_id") or f"rag_gold_{hashlib.sha1((case.get('question') or now).encode('utf-8')).hexdigest()[:12]}")
        payload = _normalize_gold_case({**case, "case_id": case_id})
        with self._connection() as conn:
            existing = conn.execute("SELECT created_at FROM rag_gold_case WHERE case_id = ?", (case_id,)).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO rag_gold_case(
                    case_id, collection, question, expected_chunk_ids_json, expected_paths_json,
                    expected_keywords_json, metadata_json, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    collection = excluded.collection,
                    question = excluded.question,
                    expected_chunk_ids_json = excluded.expected_chunk_ids_json,
                    expected_paths_json = excluded.expected_paths_json,
                    expected_keywords_json = excluded.expected_keywords_json,
                    metadata_json = excluded.metadata_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["case_id"],
                    payload["collection"],
                    payload["question"],
                    json.dumps(payload["expected_chunk_ids"], ensure_ascii=False),
                    json.dumps(payload["expected_paths"], ensure_ascii=False),
                    json.dumps(payload["expected_keywords"], ensure_ascii=False),
                    json.dumps(payload["metadata"], ensure_ascii=False),
                    1 if payload["enabled"] else 0,
                    created_at,
                    now,
                ),
            )
        return {**payload, "created_at": created_at, "updated_at": now}

    def delete_gold_case(self, case_id: str) -> bool:
        with self._connection() as conn:
            removed = conn.execute("DELETE FROM rag_gold_case WHERE case_id = ?", (case_id,)).rowcount
        return bool(removed)

    # 手动添加知识笔记 
    def add_note(self, collection: str, path: str, content: str) -> dict[str, str]:
        safe_path = path.strip() or "manual-note"
        chunk_id = f"{safe_path}#note-{self._slug(content)[:24]}"
        now = utc_now_iso()
        content_hash = _content_hash([{"content": content}])
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT id, version FROM rag_document WHERE collection = ? AND path = ? AND is_current = 1 ORDER BY version DESC LIMIT 1",
                (collection, safe_path),
            ).fetchone()
            version = int(existing["version"] or 1) if existing else 1
            if existing:
                conn.execute(
                    "UPDATE rag_document SET size = ?, created_at = ?, content_hash = ? WHERE id = ?",
                    (len(content), now, content_hash, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO rag_document(collection, path, size, created_at, content_hash, version, is_current, acl_json) VALUES (?, ?, ?, ?, ?, 1, 1, ?)",
                    (collection, safe_path, len(content), now, content_hash, '["*"]'),
                )
            conn.execute(
                "INSERT INTO rag_chunk(collection, chunk_id, path, content, created_at, document_version) VALUES (?, ?, ?, ?, ?, ?)",
                (collection, chunk_id, safe_path, content, now, version),
            )
        return {"collection": collection, "chunk_id": chunk_id, "path": safe_path}

    # 删除知识笔记
    def delete_note(self, collection: str, path: str) -> bool:
        with self._connection() as conn:
            removed = conn.execute(
                "DELETE FROM rag_chunk WHERE collection = ? AND path = ?", (collection, path)
            ).rowcount
            conn.execute("DELETE FROM rag_document WHERE collection = ? AND path = ?", (collection, path))
        return bool(removed)

    def status(self) -> dict[str, Any]:
        return {
            "kind": "sqlite",
            "database_path": str(self.db_path),
            "retrieval": "hybrid_bm25_token_rrf",
            "embedding_source": None,
            "reranker": _config().get("JAYCODE_RAG_RERANKER", "off"),
        }

    def _slug(self, text: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text.strip().lower()).strip("-")
        return slug or "note"

# EmbeddingProvider — 向量化服务
class EmbeddingProvider:
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.model = _config().get("JAYCODE_EMBEDDING_MODEL", "text-embedding-3-small")
        self._last_source = "not_used"

    @property
    def source(self) -> str:
        return self._last_source

    # 入库时：批量向量化
    # 一次 API 调用处理所有文本，比逐条调快得多
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        config = _config()
        api_key = config.get("OPENAI_API_KEY", "")
        # 文本发给 OpenAI，返回 1536 维浮点数向量。语义相近的文本，向量距离也近。
        if api_key:
            try:
                from langchain_openai import OpenAIEmbeddings

                kwargs: dict[str, Any] = {"model": self.model, "api_key": api_key}
                if config.get("OPENAI_BASE_URL"):
                    kwargs["base_url"] = config["OPENAI_BASE_URL"]
                embeddings = OpenAIEmbeddings(**kwargs)
                vectors = embeddings.embed_documents(texts)
                self._last_source = "openai"
                return [_fit_dimension(vector, self.dimension) for vector in vectors]
            except Exception as exc:  # noqa: BLE001 - embedding falls back to deterministic local mode
                self._last_error = str(exc)
        self._last_source = "hash_fallback"
        return [self._hash_embedding(text) for text in texts]
    
    # 搜索时：单条向量化
    # 只向量化用户这一条问题，然后用这个向量去数据库里找最相似的切片。
    def embed_query(self, text: str) -> list[float]:
        config = _config()
        api_key = config.get("OPENAI_API_KEY", "")
        if api_key:
            try:
                from langchain_openai import OpenAIEmbeddings

                kwargs: dict[str, Any] = {"model": self.model, "api_key": api_key}
                if config.get("OPENAI_BASE_URL"):
                    kwargs["base_url"] = config["OPENAI_BASE_URL"]
                embeddings = OpenAIEmbeddings(**kwargs)
                self._last_source = "openai"
                return _fit_dimension(embeddings.embed_query(text), self.dimension)
            except Exception as exc:  # noqa: BLE001 - embedding falls back to deterministic local mode
                self._last_error = str(exc)
        self._last_source = "hash_fallback"
        return self._hash_embedding(text)

    # 本地 hash 伪向量（降级方案）
    def _hash_embedding(self, text: str) -> list[float]:
        #第一步：初始化空向量
        vector = [0.0] * self.dimension

        # 第二步：分词
        # 把文本拆成 token：
        # 英文：至少 2 个字符的单词
        # 中文：单个汉字
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fa5]{1,}", text.lower())
        if not tokens:
            tokens = [text[:64] or "empty"]

        # 第三步：每个 token 在向量上"投票"
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest() # 32 字节 hash
            index = int.from_bytes(digest[:4], "big") % self.dimension # 取前4字节 → 0~1535
            sign = 1.0 if digest[4] % 2 == 0 else -1.0 # 第5字节奇偶 → 正或负
            vector[index] += sign # 在对应位置 +1 或 -1

        # 第四步：归一化
        # 把向量缩放到长度为 1，确保向量比较时不受绝对值影响。
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class PgVectorRagStore:
    def __init__(self, database_url: str | None = None):
        config = _config()
        self.database_url = database_url or config.get("DATABASE_URL") or config.get("PGVECTOR_DATABASE_URL", "")
        self.dimension = int(config.get("JAYCODE_EMBEDDING_DIM", "1536") or 1536)
        self.embedding = EmbeddingProvider(self.dimension)
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for pgvector RAG store")
        # 建表
        self._init_schema()

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required. Install with: pip install -e \".[vector]\"") from exc
        return psycopg.connect(self.database_url)

    # 建表
    def _init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 创建 pgvector 扩展
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rag_document (
                        id BIGSERIAL PRIMARY KEY,
                        collection TEXT NOT NULL,
                        path TEXT NOT NULL,
                        size INTEGER,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(collection, path)
                    )
                    """
                )
                # rag_chunk 多了 embedding 字段
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS rag_chunk (
                        id BIGSERIAL PRIMARY KEY,
                        collection TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding vector({self.dimension}) NOT NULL,
                        embedding_source TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(collection, chunk_id)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_document_collection ON rag_document(collection)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunk_collection ON rag_chunk(collection)"
                )
                # 向量索引（加速检索的关键）
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunk_embedding ON rag_chunk USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
                )
                cur.execute("ALTER TABLE rag_document ADD COLUMN IF NOT EXISTS content_hash TEXT")
                cur.execute("ALTER TABLE rag_document ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1")
                cur.execute("ALTER TABLE rag_document ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE")
                cur.execute("ALTER TABLE rag_document ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ")
                # ACL 用 JSONB 而不是 TEXT
                cur.execute("ALTER TABLE rag_document ADD COLUMN IF NOT EXISTS acl_json JSONB NOT NULL DEFAULT '[\"*\"]'::jsonb")
                cur.execute("ALTER TABLE rag_chunk ADD COLUMN IF NOT EXISTS document_version INTEGER NOT NULL DEFAULT 1")
                cur.execute("ALTER TABLE rag_chunk ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb")
                cur.execute("ALTER TABLE rag_document DROP CONSTRAINT IF EXISTS rag_document_collection_path_key")
                cur.execute("ALTER TABLE rag_chunk DROP CONSTRAINT IF EXISTS rag_chunk_collection_chunk_id_key")
                # 主键约束从 (collection, path) 改为 (collection, path, version)
                # 因为同一个文档可以有多个版本
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_document_version ON rag_document(collection, path, version)")
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_chunk_version ON rag_chunk(collection, chunk_id, document_version)") 
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rag_gold_case (
                        case_id TEXT PRIMARY KEY,
                        collection TEXT NOT NULL,
                        question TEXT NOT NULL,
                        expected_chunk_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        expected_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        expected_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            conn.commit()
    
    # 入库（多了向量化步骤）
    def ingest(self, collection: str, documents: list[dict[str, Any]], chunks: list[dict[str, str]]) -> dict[str, int]:
        grouped = _group_chunks(chunks)
        now = utc_now_iso()
        changed_chunks: list[tuple[dict[str, str], int]] = []
        changed_documents = 0
        # 阶段一：逐文档处理（判断是否变化 + 版本管理）
        with self._connect() as conn:
            with conn.cursor() as cur:

                # 第一步：判断哪些文档变了（和 SQLite 版一样）
                for doc in documents:
                    path = str(doc["path"])
                    content_hash = _content_hash(grouped.get(path, []))# 计算新内容的 hash
                    # 查数据库中当前版本
                    cur.execute(
                        """
                        SELECT id, content_hash, version, acl_json
                        FROM rag_document
                        WHERE collection = %s AND path = %s AND is_current = TRUE
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (collection, path),
                    )
                    existing = cur.fetchone()
                    
                    # 内容没变 → 跳过
                    if existing and existing[1] == content_hash:
                        continue
                    
                    # 内容变了 → 版本号 +1
                    changed_documents += 1
                    version = int(existing[2] or 0) + 1 if existing else 1
                    acl_json = existing[3] if existing else ["*"] # 继承旧权限
                    
                    # 旧版本标记为非当前
                    if existing:
                        cur.execute("UPDATE rag_document SET is_current = FALSE, valid_to = %s WHERE id = %s", (now, existing[0]))
                    
                    # 新版本入库
                    cur.execute(
                        """
                        INSERT INTO rag_document(collection, path, size, created_at, content_hash, version, is_current, acl_json)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s::jsonb)
                        """,
                        (collection, path, doc.get("size"), now, content_hash, version, _json_text(acl_json)),
                    )

                    # 删除该版本的旧切片，收集新切片
                    cur.execute(
                        "DELETE FROM rag_chunk WHERE collection = %s AND path = %s AND document_version = %s",
                        (collection, path, version),
                    )
                    for chunk in grouped.get(path, []):
                        changed_chunks.append((chunk, version))

                # 阶段二：批量向量化 + 入库
                # 一次性向量化所有新切片
                vectors = self.embedding.embed_documents([chunk["content"] for chunk, _version in changed_chunks])
                
                # 逐条入库（带向量）
                for (chunk, version), vector in zip(changed_chunks, vectors, strict=False):
                    cur.execute(
                        """
                        INSERT INTO rag_chunk(collection, chunk_id, path, content, metadata_json, embedding, embedding_source, created_at, document_version)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector, %s, %s, %s)
                        """,
                        (
                            collection,
                            chunk["chunk_id"],
                            chunk["path"],
                            chunk["content"],
                            _json_text(chunk.get("metadata") or {}),
                            _vector_literal(vector),
                            self.embedding.source,
                            now,
                            version,
                        ),
                    )
            conn.commit()
        return {"document_count": len(documents), "chunk_count": len(chunks), "changed_document_count": changed_documents, "changed_chunk_count": len(changed_chunks)}

   # 混合检索
    def query(self, collection: str, question: str, limit: int = 5, actor_id: str = "local-user") -> list[dict[str, Any]]:
        # 第一步：问题转向量
        vector = self.embedding.embed_query(question)
        with self._connect() as conn:  # noqa: SIM117 - cursor lifetime is nested for PostgreSQL transactions
            with conn.cursor() as cur:
                # 第二步：向量检索
                # <=> 是 pgvector 的余弦距离运算符，值越小越相似。1 - 距离 转成相似度分数
                cur.execute(
                    """
                    SELECT c.chunk_id, c.path, c.content, c.metadata_json, 1 - (c.embedding <=> %s::vector) AS vector_score, d.acl_json
                    FROM rag_chunk c JOIN rag_document d
                      ON c.collection = d.collection AND c.path = d.path AND c.document_version = d.version
                    WHERE c.collection = %s AND d.is_current = TRUE
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (_vector_literal(vector), collection, _vector_literal(vector), max(limit * 8, 60)),
                )
                rows = cur.fetchall()
        # 第三步：ACL 过滤
        visible = [
            {"chunk_id": row[0], "path": row[1], "content": str(row[2]), "metadata": row[3] or {}, "vector_score": float(row[4] or 0)}
            for row in rows
            if _acl_allows(_json_text(row[5]), actor_id) # 只保留用户有权看的
        ]
        # 第四步：混合排序 + 可选重排
        ranked = _rank_hybrid(question, visible, vector_score_key="vector_score")
        reranked = _rerank_candidates(question, ranked[: max(limit * 4, 20)])
        return [_public_rag_result(item) for item in reranked[:limit]]

    # 列出文档（带 ACL 过滤）
    def list_documents(self, collection: str | None = None, actor_id: str = "local-user") -> list[dict[str, Any]]:
        with self._connect() as conn:  # noqa: SIM117 - cursor lifetime is nested for PostgreSQL transactions
            with conn.cursor() as cur:
                if collection:
                    cur.execute(
                        """
                        SELECT collection, path, size, created_at, version, is_current, valid_to, acl_json
                        FROM rag_document
                        WHERE collection = %s
                        ORDER BY path, version DESC
                        """,
                        (collection,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT collection, path, size, created_at, version, is_current, valid_to, acl_json
                        FROM rag_document
                        ORDER BY collection, path, version DESC
                        """
                    )
                rows = cur.fetchall()
        # 返回时格式化时间、过滤 ACL
        return [
            {
                "collection": row[0],
                "path": row[1],
                "size": row[2],
                "created_at": _china_minute(row[3]),
                "version": row[4],
                "is_current": bool(row[5]),
                "valid_to": _china_minute(row[6]) if row[6] else None,
            }
            for row in rows
            if _acl_allows(_json_text(row[7]), actor_id)
        ]

    # 设置文档权限
    def set_document_acl(self, collection: str, path: str, principals: list[str]) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 只更新当前版本。principals 会去重排序
                # 保证 ["bob","alice"] 和 ["alice","bob"] 一致
                cur.execute(
                    "UPDATE rag_document SET acl_json = %s::jsonb WHERE collection = %s AND path = %s AND is_current = TRUE",
                    (json.dumps(sorted(set(principals or ["*"]))), collection, path),
                )
                updated = cur.rowcount
            conn.commit()
        return bool(updated)

    # 手动添加知识笔记
    def add_note(self, collection: str, path: str, content: str) -> dict[str, str]:
        safe_path = path.strip() or "manual-note"
        chunk_id = f"{safe_path}#note-{_slug(content)[:24]}"
        now = utc_now_iso()
        vector = self.embedding.embed_query(content)
        content_hash = _content_hash([{"content": content}])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, version FROM rag_document
                    WHERE collection = %s AND path = %s AND is_current = TRUE
                    ORDER BY version DESC LIMIT 1
                    """,
                    (collection, safe_path),
                )
                existing = cur.fetchone()
                version = int(existing[1] or 1) if existing else 1
                if existing:
                    cur.execute(
                        "UPDATE rag_document SET size = %s, created_at = %s, content_hash = %s WHERE id = %s",
                        (len(content), now, content_hash, existing[0]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO rag_document(collection, path, size, created_at, content_hash, version, is_current, acl_json)
                        VALUES (%s, %s, %s, %s, %s, 1, TRUE, %s::jsonb)
                        """,
                        (collection, safe_path, len(content), now, content_hash, '["*"]'),
                    )
                cur.execute(
                    """
                    INSERT INTO rag_chunk(collection, chunk_id, path, content, embedding, embedding_source, created_at, document_version)
                    VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s)
                    ON CONFLICT(collection, chunk_id, document_version)
                    DO UPDATE SET content = EXCLUDED.content,
                                  embedding = EXCLUDED.embedding,
                                  embedding_source = EXCLUDED.embedding_source,
                                  created_at = EXCLUDED.created_at
                    """,
                    (
                        collection,
                        chunk_id,
                        safe_path,
                        content,
                        _vector_literal(vector),
                        self.embedding.source,
                        now,
                        version,
                    ),
                )
            conn.commit()
        return {"collection": collection, "chunk_id": chunk_id, "path": safe_path}

    def delete_note(self, collection: str, path: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_chunk WHERE collection = %s AND path = %s", (collection, path))
                removed = cur.rowcount
                cur.execute("DELETE FROM rag_document WHERE collection = %s AND path = %s", (collection, path))
            conn.commit()
        return bool(removed)

    def list_gold_cases(self, collection: str | None = None, include_disabled: bool = False) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if collection:
            clauses.append("collection = %s")
            params.append(collection)
        if not include_disabled:
            clauses.append("enabled = TRUE")
        query = "SELECT case_id, collection, question, expected_chunk_ids_json, expected_paths_json, expected_keywords_json, metadata_json, enabled, created_at, updated_at FROM rag_gold_case"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:  # noqa: SIM117 - cursor lifetime is nested for PostgreSQL transactions
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [
            _gold_row_to_dict(
                {
                    "case_id": row[0],
                    "collection": row[1],
                    "question": row[2],
                    "expected_chunk_ids_json": _json_text(row[3]),
                    "expected_paths_json": _json_text(row[4]),
                    "expected_keywords_json": _json_text(row[5]),
                    "metadata_json": _json_text(row[6]),
                    "enabled": row[7],
                    "created_at": str(row[8]),
                    "updated_at": str(row[9]),
                }
            )
            for row in rows
        ]

    def save_gold_case(self, case: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        case_id = str(case.get("case_id") or f"rag_gold_{hashlib.sha1((case.get('question') or now).encode('utf-8')).hexdigest()[:12]}")
        payload = _normalize_gold_case({**case, "case_id": case_id})
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM rag_gold_case WHERE case_id = %s", (case_id,))
                existing = cur.fetchone()
                created_at = str(existing[0]) if existing else now
                cur.execute(
                    """
                    INSERT INTO rag_gold_case(
                        case_id, collection, question, expected_chunk_ids_json, expected_paths_json,
                        expected_keywords_json, metadata_json, enabled, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
                    ON CONFLICT(case_id) DO UPDATE SET
                        collection = EXCLUDED.collection,
                        question = EXCLUDED.question,
                        expected_chunk_ids_json = EXCLUDED.expected_chunk_ids_json,
                        expected_paths_json = EXCLUDED.expected_paths_json,
                        expected_keywords_json = EXCLUDED.expected_keywords_json,
                        metadata_json = EXCLUDED.metadata_json,
                        enabled = EXCLUDED.enabled,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        payload["case_id"],
                        payload["collection"],
                        payload["question"],
                        json.dumps(payload["expected_chunk_ids"], ensure_ascii=False),
                        json.dumps(payload["expected_paths"], ensure_ascii=False),
                        json.dumps(payload["expected_keywords"], ensure_ascii=False),
                        json.dumps(payload["metadata"], ensure_ascii=False),
                        payload["enabled"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        return {**payload, "created_at": created_at, "updated_at": now}

    def delete_gold_case(self, case_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_gold_case WHERE case_id = %s", (case_id,))
                removed = cur.rowcount
            conn.commit()
        return bool(removed)

    def status(self) -> dict[str, Any]:
        return {
            "kind": "pgvector",
            "database_url_configured": bool(self.database_url),
            "embedding_model": self.embedding.model,
            "embedding_source": self.embedding.source,
            "embedding_dim": self.dimension,
            "retrieval": "vector_bm25_rrf",
            "reranker": _config().get("JAYCODE_RAG_RERANKER", "off"),
        }


def create_rag_store() -> SQLiteRagStore | PgVectorRagStore:
    kind = _config().get("JAYCODE_RAG_STORE", "sqlite").lower()
    if kind == "pgvector":
        return PgVectorRagStore()
    return SQLiteRagStore()


def _config() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in [
        "JAYCODE_RAG_STORE",
        "PGVECTOR_DATABASE_URL",
        "DATABASE_URL",
        "JAYCODE_EMBEDDING_MODEL",
        "JAYCODE_EMBEDDING_DIM",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "JAYCODE_RAG_RERANKER",
    ]:
        if os.getenv(key):
            values[key] = os.getenv(key, "")
    return values

# 不同模型返回的向量维度可能不同，这个函数确保存入数据库的向量维度一致
def _fit_dimension(vector: list[float], dimension: int) -> list[float]:
    values = [float(value) for value in vector]
    if len(values) == dimension:
        return values
    if len(values) > dimension:
        return values[:dimension]
    return values + [0.0] * (dimension - len(values))


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text.strip().lower()).strip("-")
    return slug or "note"


def _group_chunks(chunks: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for chunk in chunks:
        grouped.setdefault(str(chunk["path"]), []).append(chunk)
    return grouped


def _content_hash(chunks: list[dict[str, str]]) -> str:
    content = "\n".join(str(chunk.get("content") or "") for chunk in chunks)
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fa5]{1,}", text.lower())


def _rank_hybrid(question: str, rows: list[dict[str, Any]], vector_score_key: str | None = None) -> list[dict[str, Any]]:
    if not rows:
        return []
    query_terms = _tokens(question)
    corpus_tokens = [_tokens(str(row.get("content") or "")) for row in rows]
    bm25_scores = _bm25_scores(query_terms, corpus_tokens)
    semantic_scores = [
        float(row.get(vector_score_key) or 0.0) if vector_score_key else _token_overlap(query_terms, tokens)
        for row, tokens in zip(rows, corpus_tokens, strict=False)
    ]
    bm25_rank = _rank_positions(bm25_scores)
    semantic_rank = _rank_positions(semantic_scores)
    ranked: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        score = (1 / (60 + bm25_rank[index])) + (1 / (60 + semantic_rank[index]))
        score += bm25_scores[index] * 0.001 + semantic_scores[index] * 0.05
        if score > 0 or not query_terms:
            ranked.append(
                {
                    **row,
                    "score": score,
                    "bm25_score": bm25_scores[index],
                    "semantic_score": semantic_scores[index],
                    "retrieval_mode": "vector_bm25_rrf" if vector_score_key else "hybrid_bm25_token_rrf",
                }
            )
    ranked.sort(key=lambda item: float(item["score"]), reverse=True)
    return ranked


def _bm25_scores(query_terms: list[str], documents: list[list[str]]) -> list[float]:
    if not query_terms or not documents:
        return [0.0 for _ in documents]
    k1 = 1.5
    b = 0.75
    avgdl = sum(len(doc) for doc in documents) / max(1, len(documents))
    df = {term: sum(1 for doc in documents if term in set(doc)) for term in set(query_terms)}
    scores: list[float] = []
    for doc in documents:
        doc_len = len(doc) or 1
        freqs = {term: doc.count(term) for term in set(query_terms)}
        score = 0.0
        for term in query_terms:
            tf = freqs.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (len(documents) - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(avgdl, 1))))
        scores.append(score)
    return scores


def _token_overlap(query_terms: list[str], doc_terms: list[str]) -> float:
    if not query_terms:
        return 0.0
    return len(set(query_terms) & set(doc_terms)) / max(1, len(set(query_terms)))


def _rank_positions(scores: list[float]) -> list[int]:
    ordered = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    ranks = [len(scores) + 1] * len(scores)
    for rank, index in enumerate(ordered, start=1):
        ranks[index] = rank
    return ranks


def _rerank_candidates(question: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if _config().get("JAYCODE_RAG_RERANKER", "off").lower() != "llm" or len(candidates) <= 1:
        return candidates
    try:
        candidate_lines = [
            {"chunk_id": item["chunk_id"], "path": item["path"], "preview": str(item["content"])[:420]}
            for item in candidates[:12]
        ]
        response = llm_provider.generate_with_status(
            "You are a RAG reranker. Return JSON only: {\"ordered_chunk_ids\":[...]}",
            json.dumps({"question": question, "candidates": candidate_lines}, ensure_ascii=False),
            json.dumps({"ordered_chunk_ids": [item["chunk_id"] for item in candidates]}, ensure_ascii=False),
            agent="rag_reranker",
            prompt_version="rag_reranker.v1",
            response_schema=RerankResponse,
            use_active_prompt=False,
        )
        parsed = llm_provider.parse_structured(response, RerankResponse)
        ordered = [str(item) for item in parsed.ordered_chunk_ids]
        if not ordered:
            return candidates
        rank = {chunk_id: index for index, chunk_id in enumerate(ordered)}
        reranked = sorted(candidates, key=lambda item: (rank.get(str(item.get("chunk_id")), len(rank) + 100), -float(item.get("score") or 0)))
        for index, item in enumerate(reranked):
            item["rerank_score"] = max(0, len(reranked) - index)
            item["retrieval_mode"] = f"{item.get('retrieval_mode', 'hybrid')}_llm_rerank"
        return reranked
    except Exception as exc:  # noqa: BLE001 - reranking is optional and retrieval remains available
        _ = exc
        return candidates


def _public_rag_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": item.get("chunk_id"),
        "path": item.get("path"),
        "score": round(float(item.get("score") or 0), 6),
        "keyword_score": round(float(item.get("bm25_score") or 0), 4),
        "semantic_score": round(float(item.get("semantic_score") or 0), 4),
        "rerank_score": item.get("rerank_score"),
        "retrieval_mode": item.get("retrieval_mode", "hybrid_bm25_token_rrf"),
        "content": str(item.get("content") or "")[:800],
    }


def _normalize_gold_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id") or "").strip(),
        "collection": str(case.get("collection") or "default").strip() or "default",
        "question": str(case.get("question") or "").strip(),
        "expected_chunk_ids": [str(item) for item in case.get("expected_chunk_ids", [])],
        "expected_paths": [str(item) for item in case.get("expected_paths", [])],
        "expected_keywords": [str(item) for item in case.get("expected_keywords", [])],
        "metadata": dict(case.get("metadata") or {}),
        "enabled": bool(case.get("enabled", True)),
    }


def evaluate_gold_set(store: Any, collection: str | None = None, actor_id: str = "local-user", k: int = 5) -> dict[str, Any]:
    """Run the Gold Set and calculate Recall@K, MRR and keyword coverage."""
    cases = store.list_gold_cases(collection, include_disabled=False)
    results: list[dict[str, Any]] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    keyword_coverages: list[float] = []
    for case in cases:
        hits = store.query(case["collection"], case["question"], limit=k, actor_id=actor_id)
        expected_ids = set(case.get("expected_chunk_ids") or [])
        expected_paths = set(case.get("expected_paths") or [])
        expected_keywords = [str(item).lower() for item in case.get("expected_keywords") or []]
        relevant = [index + 1 for index, item in enumerate(hits) if item.get("chunk_id") in expected_ids or item.get("path") in expected_paths]
        recall = 1.0 if relevant else 0.0
        reciprocal_rank = 1.0 / relevant[0] if relevant else 0.0
        haystack = " ".join(str(item.get("content") or "").lower() for item in hits)
        keyword_coverage = sum(keyword in haystack for keyword in expected_keywords) / len(expected_keywords) if expected_keywords else 1.0
        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        keyword_coverages.append(keyword_coverage)
        results.append({"case_id": case["case_id"], "hit_count": len(hits), "recall_at_k": recall, "reciprocal_rank": reciprocal_rank, "keyword_coverage": round(keyword_coverage, 4)})
    count = len(results)
    return {"collection": collection, "k": k, "case_count": count, "recall_at_k": round(sum(recalls) / count, 4) if count else 0.0, "mrr": round(sum(reciprocal_ranks) / count, 4) if count else 0.0, "keyword_coverage": round(sum(keyword_coverages) / count, 4) if count else 0.0, "results": results}


def _gold_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row["case_id"],
        "collection": row["collection"],
        "question": row["question"],
        "expected_chunk_ids": _json_list(row.get("expected_chunk_ids_json")),
        "expected_paths": _json_list(row.get("expected_paths_json")),
        "expected_keywords": _json_list(row.get("expected_keywords_json")),
        "metadata": _json_dict(row.get("metadata_json")),
        "enabled": bool(row.get("enabled")),
        "created_at": _china_minute(row.get("created_at")),
        "updated_at": _china_minute(row.get("updated_at")),
    }


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        return [str(item) for item in json.loads(str(value or "[]"))]
    except (TypeError, json.JSONDecodeError):
        return []


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _china_minute(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}, \d{2}:\d{2}$", text):
        return text
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.strftime("%Y-%m-%d, %H:%M")
        return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d, %H:%M")
    except ValueError:
        return text[:16].replace("T", ", ")


def _acl_allows(raw_acl: Any, actor_id: str) -> bool:
    if isinstance(raw_acl, list):
        principals = [str(item) for item in raw_acl]
        return "*" in principals or actor_id in principals
    try:
        principals = json.loads(str(raw_acl or '["*"]'))
    except json.JSONDecodeError:
        principals = ["*"]
    return "*" in principals or actor_id in principals


class _LazyRagStore:
    """Delay backend construction until use so importing RAG helpers has no I/O."""

    def __init__(self) -> None:
        self._store: SQLiteRagStore | PgVectorRagStore | None = None

    def __getattr__(self, name: str) -> Any:
        if self._store is None:
            self._store = create_rag_store()
        return getattr(self._store, name)


rag_store = _LazyRagStore()
