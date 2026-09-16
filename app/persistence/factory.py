"""Application-wide persistence selection with an explicit all-domain bundle."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings
from app.persistence.contracts import (
    AuditStore,
    BenchmarkStore,
    LlmStore,
    MarketplaceStore,
    McpStore,
    MemoryStore,
    PromptStore,
    RagStore,
    ReviewStore,
    SkillStore,
    TaskStore,
    WorkflowStore,
    unsupported_postgres_domains,
)


class PersistenceConfigurationError(RuntimeError):
    """The configured backend cannot safely serve every persistence domain."""


@dataclass(frozen=True)
class PersistenceStores:
    """All public persistence-domain handles for one configured backend."""

    task: TaskStore
    workflow: WorkflowStore
    review: ReviewStore
    skill: SkillStore
    mcp: McpStore
    marketplace: MarketplaceStore
    audit: AuditStore
    memory: MemoryStore
    llm: LlmStore
    prompt: PromptStore
    benchmark: BenchmarkStore
    rag: RagStore
    backend: str

    def ping(self) -> None:
        """Fail if the selected backend cannot answer a trivial read."""
        if self.backend == "postgres":
            with self.task.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return
        with self.task._connect() as conn:
            conn.execute("SELECT 1").fetchone()


def _sqlite_stores() -> PersistenceStores:
    from app.persistence.memory_store import SQLiteMemoryStore
    from app.persistence.rag_store import SQLiteRagStore
    from app.persistence.sqlite_store import SQLiteTaskStore

    task = SQLiteTaskStore()
    memory = SQLiteMemoryStore(task.db_path)
    rag = SQLiteRagStore(task.db_path)
    return PersistenceStores(
        task=task,
        workflow=task,
        review=task,
        skill=task,
        mcp=task,
        marketplace=task,
        audit=task,
        memory=memory,
        llm=task,
        prompt=task,
        benchmark=task,
        rag=rag,
        backend="sqlite",
    )


def _postgres_stores() -> PersistenceStores:
    from app.persistence.postgres_config import validate_matching_postgres_targets

    if not settings.database_url:
        raise PersistenceConfigurationError("JAYCODE_PERSISTENCE_STORE=postgres requires DATABASE_URL")
    validate_matching_postgres_targets(settings.database_url, settings.pgvector_database_url)
    unsupported = unsupported_postgres_domains()
    if unsupported:
        details = ", ".join(f"{name}({contract.postgres_status})" for name, contract in unsupported.items())
        raise PersistenceConfigurationError(
            "PostgreSQL persistence is not ready; refusing mixed persistence. "
            f"Not activation-ready domains: {details}."
        )
    # Stage 2 enables construction after each domain has a verified contract.
    raise PersistenceConfigurationError("PostgreSQL persistence schema is not verified for activation.")


@lru_cache(maxsize=1)
def get_persistence_stores() -> PersistenceStores:
    """Build one complete backend bundle; mixed SQLite/PostgreSQL is forbidden."""
    backend = settings.jaycode_persistence_store.strip().lower()
    if backend == "sqlite":
        if settings.jaycode_rag_store.strip().lower() not in {"sqlite", ""}:
            raise PersistenceConfigurationError("SQLite persistence requires JAYCODE_RAG_STORE=sqlite.")
        return _sqlite_stores()
    if backend == "postgres":
        return _postgres_stores()
    raise PersistenceConfigurationError("JAYCODE_PERSISTENCE_STORE must be sqlite or postgres")
