"""Post-commit PostgreSQL smoke checks for the real Jaycode cutover.

This command is intentionally write-capable and therefore requires an exact
confirmation value.  Its records use the ``cutover_smoke_`` prefix and are
removed after verification; the successful write itself is the commit proof.
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4

from app.persistence.migrate import CUTOVER_DATABASE_NAME


def _assert_postgres_runtime() -> object:
    from app.core.config import settings
    from app.persistence.factory import get_persistence_stores

    if settings.jaycode_persistence_store.strip().lower() != "postgres":
        raise RuntimeError("Post-cutover smoke requires JAYCODE_PERSISTENCE_STORE=postgres.")
    get_persistence_stores.cache_clear()
    stores = get_persistence_stores()
    if stores.backend != "postgres":
        raise RuntimeError("Post-cutover smoke refused a non-PostgreSQL persistence bundle.")
    stores.ping()
    return stores


def run_smoke() -> dict[str, object]:
    """Write and read a deterministic, self-cleaning representative record set."""
    stores = _assert_postgres_runtime()
    suffix = uuid4().hex
    task_id = f"cutover_smoke_task_{suffix}"
    workflow_id = f"cutover_smoke_workflow_{suffix}"
    trace_id = f"cutover_smoke_trace_{suffix}"
    run_id = f"cutover_smoke_benchmark_{suffix}"
    memory_id = ""
    collection = f"cutover_smoke_rag_{suffix}"
    audit_id = ""
    plugin_id = f"cutover_smoke_plugin_{suffix}"
    skill_code = f"cutover.smoke.{suffix}"
    server_id = f"cutover_smoke_mcp_{suffix}"
    install_id = f"cutover_smoke_install_{suffix}"
    checks: list[str] = []
    try:
        stores.task.create_task(task_id, "cutover smoke", None, "queued", {"idempotency_key": task_id}, {"synthetic": True})
        claimed = stores.task.claim_task(task_id, "cutover-smoke-worker", lease_seconds=30)
        if not claimed:
            raise RuntimeError("PostgreSQL Worker claim failed during cutover smoke.")
        stores.task.save_task_bundle(
            task_id, "completed", "cutover smoke complete", [("cutover_smoke", "result", {"ok": True})],
            [{"event_id": f"cutover_smoke_event_{suffix}", "task_id": task_id, "type": "cutover_smoke", "status": "completed"}],
        )
        if stores.task.get_task(task_id)["status"] != "completed":
            raise RuntimeError("PostgreSQL task completion was not persisted.")
        checks.append("task_worker")

        stores.workflow.save_workflow(workflow_id, "cutover smoke", "PostgreSQL cutover validation", [{"id": "start"}], [])
        if not stores.workflow.get_workflow(workflow_id):
            raise RuntimeError("PostgreSQL workflow write was not persisted.")
        stores.review.record_review_action(task_id, "verified", "cutover smoke")
        checks.extend(("workflow", "review"))

        stores.skill.seed_builtin_skills(
            {"plugin_id": plugin_id, "name": "Cutover smoke", "version": "1", "source_type": "builtin"},
            [{"code": skill_code, "name": "Cutover smoke", "execution_type": "prompt", "input_schema": {}, "output_schema": {}, "permissions": [], "version": "1"}],
        )
        if not stores.skill.get_skill(skill_code):
            raise RuntimeError("PostgreSQL Skill write was not persisted.")
        stores.mcp.save_mcp_server({"server_id": server_id, "name": "Cutover smoke", "command": "synthetic", "args": [], "env": {}})
        stores.mcp.upsert_mcp_tool({"server_id": server_id, "name": "smoke", "input_schema": {"type": "object"}})
        if not stores.mcp.list_mcp_tools(server_id):
            raise RuntimeError("PostgreSQL MCP write was not persisted.")
        stores.marketplace.save_marketplace_install({
            "install_id": install_id, "package_id": f"cutover_smoke_package_{suffix}", "name": "Cutover smoke",
            "package_type": "skill", "version": "1", "source_url": "builtin://cutover", "status": "previewed",
            "approval_status": "pending", "summary": {}, "manifest": {},
        })
        if not stores.marketplace.list_marketplace_installs(package_type="skill"):
            raise RuntimeError("PostgreSQL Marketplace write was not persisted.")
        checks.extend(("skill", "mcp", "marketplace"))

        audit = stores.audit.save_security_audit({
            "request_id": f"cutover_smoke_request_{suffix}", "actor_id": "cutover-smoke", "role": "admin",
            "action": "cutover_smoke", "resource_type": "migration", "resource_id": task_id,
            "status": "completed", "metadata": {"synthetic": True},
        })
        audit_id = str(audit["audit_id"])
        if not stores.audit.list_security_audits(actor_id="cutover-smoke", action="cutover_smoke"):
            raise RuntimeError("PostgreSQL audit write was not persisted.")
        checks.append("audit")

        stores.llm.save_llm_trace({
            "trace_id": trace_id, "agent": "cutover-smoke", "prompt_version": "cutover.v1", "model": "synthetic",
            "input": {"synthetic": True}, "output": "ok", "latency_ms": 1, "token_usage": {"total_tokens": 1},
            "request_id": f"cutover_smoke_request_{suffix}", "actor_id": "cutover-smoke", "role": "admin",
        })
        stores.prompt.upsert_prompt_version({"agent": "cutover-smoke", "prompt_version": "cutover.v1", "title": "Cutover smoke", "system_suffix": "synthetic"})
        if not stores.llm.list_llm_traces(agent="cutover-smoke") or not stores.prompt.get_prompt_version("cutover-smoke", "cutover.v1"):
            raise RuntimeError("PostgreSQL LLM or prompt write was not persisted.")
        checks.extend(("llm", "prompt"))

        stores.benchmark.create_benchmark_run(run_id, "cutover smoke", "rag", {"dataset_version": "cutover"})
        stores.benchmark.append_benchmark_result({"run_id": run_id, "case_id": "smoke", "status": "passed", "input": {}, "output": {"ok": True}})
        stores.benchmark.finish_benchmark_run(run_id, "completed", {"passed": 1})
        if not stores.benchmark.get_benchmark_run(run_id):
            raise RuntimeError("PostgreSQL benchmark write was not persisted.")
        checks.append("benchmark")

        memories = stores.memory.extract_candidates(
            f"cutover smoke memory {suffix}", scope="project", scope_id=suffix,
            source_ref="cutover-smoke", actor_id="cutover-smoke",
        )
        if not memories:
            raise RuntimeError("PostgreSQL memory candidate was not created.")
        memory_id = str(memories[0]["memory_id"])
        if not stores.memory.confirm(memory_id, f"memory/{suffix}", actor_id="cutover-smoke"):
            raise RuntimeError("PostgreSQL memory confirmation failed.")
        checks.append("memory")

        rag = stores.rag
        rag.embedding.embed_documents = lambda texts: [rag.embedding._hash_embedding(text) for text in texts]
        rag.embedding.embed_query = lambda text: rag.embedding._hash_embedding(text)
        rag.ingest(collection, [{"path": "cutover.md", "size": 1}], [{"chunk_id": f"chunk_{suffix}", "path": "cutover.md", "content": "cutover smoke", "metadata": {}}])
        if not rag.query(collection, "cutover", actor_id="cutover-smoke"):
            raise RuntimeError("PostgreSQL RAG query failed after ingest.")
        checks.append("rag")
        return {"status": "passed", "database": CUTOVER_DATABASE_NAME, "checks": checks}
    finally:
        # These identifiers are generated solely for smoke validation.  The
        # write acceptance remains recorded in the cutover report, without
        # retaining synthetic operational data in the migrated dataset.
        with stores.task.connection() as connection:
            connection.execute("DELETE FROM security_audit_log WHERE audit_id=%s", (audit_id,)) if audit_id else None
            connection.execute("DELETE FROM llm_call_trace WHERE trace_id=%s", (trace_id,))
            connection.execute("DELETE FROM llm_prompt_version WHERE agent=%s", ("cutover-smoke",))
            connection.execute("DELETE FROM benchmark_run WHERE run_id=%s", (run_id,))
            connection.execute("DELETE FROM plugin_marketplace_install WHERE install_id=%s", (install_id,))
            connection.execute("DELETE FROM mcp_tool_registry WHERE server_id=%s", (server_id,))
            connection.execute("DELETE FROM mcp_server_config WHERE server_id=%s", (server_id,))
            connection.execute("DELETE FROM skill_execution_log WHERE skill_code=%s", (skill_code,))
            connection.execute("DELETE FROM skill_approval WHERE skill_code=%s", (skill_code,))
            connection.execute("DELETE FROM skill_version_snapshot WHERE skill_code=%s", (skill_code,))
            connection.execute("DELETE FROM skill_registry WHERE skill_id=%s", (skill_code,))
            connection.execute("DELETE FROM skill_plugin WHERE plugin_id=%s", (plugin_id,))
            connection.execute("DELETE FROM workflow_definition WHERE workflow_id=%s", (workflow_id,))
            connection.execute("DELETE FROM human_review_action WHERE task_id=%s", (task_id,))
            connection.execute("DELETE FROM agent_task WHERE task_id=%s", (task_id,))
            connection.execute("DELETE FROM memory_lifecycle_event WHERE memory_id=%s", (memory_id,)) if memory_id else None
            connection.execute("DELETE FROM memory_record WHERE memory_id=%s", (memory_id,)) if memory_id else None
            connection.execute("DELETE FROM rag_chunk WHERE collection=%s", (collection,))
            connection.execute("DELETE FROM rag_document WHERE collection=%s", (collection,))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run explicit post-cutover PostgreSQL smoke checks")
    parser.add_argument("--confirm-postgres-commit", default="")
    args = parser.parse_args()
    if args.confirm_postgres_commit != CUTOVER_DATABASE_NAME:
        raise SystemExit(f"Use --confirm-postgres-commit {CUTOVER_DATABASE_NAME} to permit smoke writes.")
    print(json.dumps(run_smoke(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
