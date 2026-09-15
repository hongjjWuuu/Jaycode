from __future__ import annotations

from uuid import uuid4

import pytest

from app.persistence.rag_store import PgVectorRagStore
from postgres_test_config import isolated_postgres_url

DATABASE_URL = isolated_postgres_url()
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="set JAYCODE_TEST_DATABASE_URL to an isolated local test database")


def test_postgres_rag_document_acl_note_and_gold_case_contract() -> None:
    store = PgVectorRagStore(DATABASE_URL)
    store.embedding.embed_documents = lambda texts: [store.embedding._hash_embedding(text) for text in texts]
    store.embedding.embed_query = lambda text: store.embedding._hash_embedding(text)
    collection = f"contract-{uuid4().hex}"
    path = "docs/contract.md"
    case_id = f"case-{uuid4().hex}"
    try:
        saved = store.ingest(
            collection,
            [{"path": path, "size": 20}],
            [{"chunk_id": f"chunk-{case_id}", "path": path, "content": "PostgreSQL contract document", "metadata": {"line_start": 1}}],
        )
        assert saved["changed_document_count"] == 1
        assert any(item["path"] == path for item in store.list_documents(collection, actor_id="contract-user"))
        assert store.query(collection, "PostgreSQL contract", actor_id="contract-user")
        assert store.set_document_acl(collection, path, ["other-user"]) is True
        assert store.query(collection, "PostgreSQL contract", actor_id="contract-user") == []
        assert store.query(collection, "PostgreSQL contract", actor_id="other-user")
        store.add_note(collection, "memory/contract", "memory note")
        assert any(item["path"] == "memory/contract" for item in store.list_documents(collection, actor_id="other-user"))
        case = store.save_gold_case(
            {
                "case_id": case_id, "collection": collection, "question": "PostgreSQL contract",
                "expected_chunk_ids": [f"chunk-{case_id}"], "expected_paths": [path],
                "expected_keywords": ["PostgreSQL"], "enabled": True,
            }
        )
        assert case["case_id"] == case_id
        assert any(item["case_id"] == case_id for item in store.list_gold_cases(collection))
    finally:
        with store._connect() as conn:
            conn.execute("DELETE FROM rag_gold_case WHERE case_id=%s", (case_id,))
            conn.execute("DELETE FROM rag_chunk WHERE collection=%s", (collection,))
            conn.execute("DELETE FROM rag_document WHERE collection=%s", (collection,))
