from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core.config import settings
from app.persistence.contracts import DOMAIN_CONTRACTS
from app.persistence.factory import PersistenceConfigurationError, get_persistence_stores
from app.persistence.rag_store import PgVectorRagStore


def test_sqlite_bundle_exposes_every_declared_domain_and_contract_method() -> None:
    get_persistence_stores.cache_clear()
    stores = get_persistence_stores()
    assert stores.backend == "sqlite"
    assert stores.task.db_path == stores.memory.db_path == stores.rag.db_path
    for domain, contract in DOMAIN_CONTRACTS.items():
        store = getattr(stores, domain)
        missing = [method for method in contract.methods if not callable(getattr(store, method, None))]
        assert not missing, f"{domain} is missing SQLite contract methods: {missing}"


def test_postgres_factory_fails_closed_when_connection_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jaycode_persistence_store", "postgres")
    monkeypatch.setattr(settings, "database_url", "postgresql://127.0.0.1:1/jaycode_test_unavailable")
    monkeypatch.setattr(settings, "pgvector_database_url", "")
    get_persistence_stores.cache_clear()
    try:
        with pytest.raises(PersistenceConfigurationError, match="startup check failed"):
            get_persistence_stores()
    finally:
        get_persistence_stores.cache_clear()


def test_postgres_factory_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jaycode_persistence_store", "postgres")
    monkeypatch.setattr(settings, "database_url", "")
    get_persistence_stores.cache_clear()
    try:
        with pytest.raises(PersistenceConfigurationError, match="DATABASE_URL"):
            get_persistence_stores()
    finally:
        get_persistence_stores.cache_clear()


def test_pgvector_rag_preserves_public_embedding_contract() -> None:
    for method in ("source", "embed_documents", "embed_query"):
        assert callable(getattr(PgVectorRagStore, method, None))


def test_production_modules_do_not_import_global_store_singletons() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    forbidden = {"task_store", "memory_store", "rag_store"}
    violations: list[str] = []
    for path in root.rglob("*.py"):
        if "persistence" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module not in {
                "app.persistence.factory",
                "app.persistence.sqlite_store",
                "app.persistence.memory_store",
                "app.persistence.rag_store",
            }:
                continue
            names = {alias.name for alias in node.names}
            blocked = sorted(names & forbidden)
            if blocked:
                violations.append(f"{path.relative_to(root)}: {', '.join(blocked)}")
    assert not violations, "production modules must obtain stores from PersistenceStores: " + "; ".join(violations)
