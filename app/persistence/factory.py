"""Application-wide persistence store selection.

All application layers should obtain persistence handles from this module.
PostgreSQL remains deliberately fail-closed until every domain adapter has
passed the shared store contract; selecting it must never create a mixed
SQLite/PostgreSQL application.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class PersistenceStores:
    """The three persistence domains currently exposed to application code."""

    task: Any
    memory: Any
    rag: Any
    backend: str

    def ping(self) -> None:
        """Fail if the selected backend cannot answer a trivial read."""
        if self.backend == "postgres":
            with self.task.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return
        with self.task._connect() as conn:
            conn.execute("SELECT 1").fetchone()


@lru_cache(maxsize=1)
def get_persistence_stores() -> PersistenceStores:
    """Build the configured stores once per process, failing closed if partial."""
    backend = settings.jaycode_persistence_store.strip().lower()
    if backend not in {"sqlite", "postgres"}:
        raise RuntimeError("JAYCODE_PERSISTENCE_STORE must be sqlite or postgres")
    if backend == "postgres":
        from app.persistence.postgres_config import validate_matching_postgres_targets

        if not settings.database_url:
            raise RuntimeError("JAYCODE_PERSISTENCE_STORE=postgres requires DATABASE_URL")
        validate_matching_postgres_targets(settings.database_url, settings.pgvector_database_url)
        raise RuntimeError(
            "PostgreSQL persistence is not available: Task, Memory, RAG and application-domain "
            "Store contracts are not all wired. Refusing mixed persistence."
        )

    from app.persistence.memory_store import memory_store
    from app.persistence.rag_store import SQLiteRagStore
    from app.persistence.sqlite_store import task_store

    if settings.jaycode_rag_store.strip().lower() not in {"sqlite", ""}:
        raise RuntimeError(
            "SQLite persistence requires JAYCODE_RAG_STORE=sqlite; split SQLite/PostgreSQL "
            "persistence is not supported."
        )
    rag = SQLiteRagStore(task_store.db_path)

    return PersistenceStores(task=task_store, memory=memory_store, rag=rag, backend=backend)


class StoreProxy:
    """Lazy compatibility handle that resolves through the configured factory."""

    def __init__(self, domain: str) -> None:
        self._domain = domain

    def __getattr__(self, name: str) -> Any:
        store = getattr(get_persistence_stores(), self._domain)
        return getattr(store, name)


task_store = StoreProxy("task")
memory_store = StoreProxy("memory")
rag_store = StoreProxy("rag")
