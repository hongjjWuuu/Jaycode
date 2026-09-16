from __future__ import annotations

from uuid import uuid4

import pytest
from postgres_test_config import isolated_postgres_url

from app.persistence.postgres_store import PostgresTaskStore

DATABASE_URL = isolated_postgres_url()
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DATABASE_URL, reason="set JAYCODE_TEST_DATABASE_URL to an isolated local test database"),
]


def test_postgres_schema_and_task_contract_are_idempotent() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    store.init_full_schema()
    task_id = f"pg-test-{uuid4().hex}"
    review_task_id = f"pg-review-{uuid4().hex}"
    try:
        store.create_task(task_id, "contract test", None, "queued", {"idempotency_key": f"key-{task_id}"}, {"hello": "world"})
        assert store.get_task_input(task_id) == {"hello": "world"}
        claimed = store.claim_next_task(f"pg-worker-{uuid4().hex}", lease_seconds=20)
        assert claimed and claimed["task_id"] == task_id
        store.save_task_bundle(
            task_id,
            "completed",
            "done",
            [("contract", "result", {"ok": True})],
            [{"event_id": f"event-{task_id}", "task_id": task_id, "type": "task", "status": "completed", "content": "done"}],
        )
        assert store.get_task(task_id)["status"] == "completed"
        assert store.get_events_after(task_id)[0]["type"] == "task"
        assert store.get_artifacts(task_id)[0]["content"] == {"ok": True}

        store.create_task(review_task_id, "review transaction", None, "waiting_review")
        with pytest.raises(TypeError):
            store.apply_review_transition(
                review_task_id,
                "approved",
                "rollback probe",
                "queued",
                [{"event_id": f"bad-event-{review_task_id}", "data": {"not_json": object()}}],
                checkpoint={"step": "approval"},
            )
        assert store.get_task(review_task_id)["status"] == "waiting_review"
        with store.connection() as conn:
            review_count = conn.execute(
                "SELECT count(*) AS count FROM human_review_action WHERE task_id=%s",
                (review_task_id,),
            ).fetchone()["count"]
        assert review_count == 0
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM agent_task WHERE task_id=%s", (task_id,))
            conn.execute("DELETE FROM agent_task WHERE task_id=%s", (review_task_id,))


def test_postgres_mcp_store_contract() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    suffix = uuid4().hex
    server_id = f"pg-mcp-{suffix}"
    tool_name = "echo"
    call_id = f"pg-call-{suffix}"
    workflow_id = f"pg-workflow-{suffix}"
    plan_id = f"pg-learning-{suffix}"
    store.save_mcp_server(
        {"server_id": server_id, "name": server_id, "command": "python.exe", "args": ["-c", "pass"], "env": {"SAFE": "1"}}
    )
    try:
        workflow = store.save_workflow(workflow_id, "contract", "workflow contract", [{"id": "start"}], [])
        assert workflow["nodes"] == [{"id": "start"}]
        assert store.get_workflow(workflow_id)["description"] == "workflow contract"
        assert any(item["workflow_id"] == workflow_id for item in store.list_workflows())
        plan = store.save_learning_plan(plan_id, "task-contract", "topic", "beginner", [{"step": 1}], [{"q": "?"}], "report")
        assert plan["plan"] == [{"step": 1}]
        assert store.update_learning_plan_status(plan_id, "completed")["status"] == "completed"
        assert any(item["plan_id"] == plan_id for item in store.list_learning_plans("task-contract"))
        assert store.get_mcp_server(server_id)["args"] == ["-c", "pass"]
        store.upsert_mcp_tool({"server_id": server_id, "name": tool_name, "input_schema": {"type": "object"}})
        assert store.get_mcp_tool(server_id, tool_name)["input_schema"] == {"type": "object"}
        approval = store.set_mcp_tool_approval("contract-agent", server_id, tool_name, True, "approved")
        assert approval["allowed"] is True
        store.save_mcp_call_log(
            {
                "call_id": call_id, "server_id": server_id, "tool_name": tool_name,
                "agent_code": "contract-agent", "request_id": f"req-{suffix}",
                "actor_id": "contract-actor", "role": "user", "status": "completed",
                "input": {"message": "hello"}, "output": {"message": "hello"},
                "command_summary": "python.exe", "latency_ms": 3,
            }
        )
        logs = store.list_mcp_call_logs(server_id=server_id)
        assert logs[0]["call_id"] == call_id
        assert logs[0]["output"] == {"message": "hello"}
        assert store.update_mcp_tool_enabled(server_id, tool_name, False)["enabled"] is False
        assert store.update_mcp_server_status(server_id, "connected")["status"] == "connected"
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM mcp_tool_call_log WHERE call_id=%s", (call_id,))
            conn.execute("DELETE FROM mcp_tool_approval WHERE server_id=%s", (server_id,))
            conn.execute("DELETE FROM mcp_tool_registry WHERE server_id=%s", (server_id,))
            conn.execute("DELETE FROM mcp_server_config WHERE server_id=%s", (server_id,))
            conn.execute("DELETE FROM workflow_definition WHERE workflow_id=%s", (workflow_id,))
            conn.execute("DELETE FROM learning_plan WHERE plan_id=%s", (plan_id,))


def test_postgres_llm_trace_and_prompt_contract() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    suffix = uuid4().hex
    agent = f"contract-agent-{suffix}"
    trace_id = f"pg-trace-{suffix}"
    try:
        trace = store.save_llm_trace(
            {
                "trace_id": trace_id, "agent": agent, "prompt_version": "review.v1",
                "model": "mock-model", "input": {"kind": "test"}, "output": "ok",
                "fallback_used": False, "latency_ms": 7, "token_usage": {"total_tokens": 2},
                "request_id": f"req-{suffix}", "actor_id": "contract-actor", "role": "user",
            }
        )
        assert trace["trace_id"] == trace_id
        assert store.list_llm_traces(agent=agent)[0]["input"] == {"kind": "test"}
        usage = store.llm_usage_summary(agent=agent)
        assert usage["total"]["calls"] == 1
        prompt_v1 = store.upsert_prompt_version(
            {"agent": agent, "prompt_version": "review.v1", "title": "Review v1", "system_suffix": "one"}
        )
        assert prompt_v1["system_suffix"] == "one"
        store.upsert_prompt_version(
            {"agent": agent, "prompt_version": "review.v2", "title": "Review v2", "system_suffix": "two"}
        )
        assert store.set_active_prompt_version(agent, "review.v2")["is_active"] is True
        assert store.get_active_prompt_version(agent, "review")["prompt_version"] == "review.v2"
        assert len(store.list_prompt_versions(agent)) == 2
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM llm_call_trace WHERE trace_id=%s", (trace_id,))
            conn.execute("DELETE FROM llm_prompt_version WHERE agent=%s", (agent,))


def test_postgres_benchmark_run_and_results_contract() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    run_id = f"pg-benchmark-{uuid4().hex}"
    try:
        run = store.create_benchmark_run(run_id, "contract run", "rag", {"dataset_version": "test-v1"})
        assert run["status"] == "running"
        store.append_benchmark_result(
            {"run_id": run_id, "case_id": "same-case", "iteration": 1, "status": "passed", "input": {"q": "a"}, "output": {"hit": True}}
        )
        store.append_benchmark_result(
            {"run_id": run_id, "case_id": "same-case", "iteration": 2, "status": "passed", "input": {"q": "b"}, "output": {"hit": True}}
        )
        finished = store.finish_benchmark_run(run_id, "completed", {"passed": 2})
        assert finished["summary"] == {"passed": 2}
        result = store.get_benchmark_run(run_id)
        assert len(result["results"]) == 2
        assert result["results"][0]["input"]["q"] in {"a", "b"}
        assert any(item["run_id"] == run_id for item in store.list_benchmark_runs(benchmark_type="rag"))
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM benchmark_run WHERE run_id=%s", (run_id,))


def test_postgres_skill_registry_and_history_contract() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    suffix = uuid4().hex
    plugin_id = f"pg-plugin-{suffix}"
    skill_code = f"pg.skill.{suffix}"
    log_id = f"pg-skill-log-{suffix}"
    def skill(version: str) -> dict[str, object]:
        return {
            "code": skill_code, "name": "Contract Skill", "execution_type": "prompt",
            "input_schema": {}, "output_schema": {}, "permissions": [], "version": version,
        }

    try:
        store.seed_builtin_skills(
            {"plugin_id": plugin_id, "name": "Contract Plugin", "version": "1.0", "source_type": "external"},
            [skill("1.0")],
        )
        store.seed_builtin_skills(
            {"plugin_id": plugin_id, "name": "Contract Plugin", "version": "2.0", "source_type": "external"},
            [skill("2.0")],
        )
        assert any(item["plugin_id"] == plugin_id for item in store.list_skill_plugins())
        current = store.get_skill(skill_code)
        assert current["version"] == "2.0"
        assert any(item["code"] == skill_code for item in store.list_skills())
        assert store.update_skill_enabled(skill_code, False)["enabled"] is False
        assert store.set_skill_approval(skill_code, "contract-agent", True, "allowed")["allowed"] is True
        assert store.get_skill_approval(skill_code, "contract-agent")["allowed"] is True
        assert any(item["skill_code"] == skill_code for item in store.list_skill_approvals("contract-agent"))
        store.save_skill_execution_log(
            {"log_id": log_id, "skill_code": skill_code, "agent_code": "contract-agent", "status": "completed", "input": {"x": 1}, "output": {"y": 2}}
        )
        assert store.list_skill_execution_logs(skill_code=skill_code)[0]["output"] == {"y": 2}
        assert any(item["version"] == "1.0" for item in store.list_skill_versions(skill_code))
        assert store.rollback_skill_version(skill_code, "1.0")["version"] == "1.0"
        removed = store.uninstall_skill_plugin(plugin_id)
        assert removed["removed_skill_count"] == 1
        assert store.get_skill(skill_code) is None
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM skill_execution_log WHERE log_id=%s", (log_id,))
            conn.execute("DELETE FROM skill_approval WHERE skill_code=%s", (skill_code,))
            conn.execute("DELETE FROM skill_version_snapshot WHERE skill_code=%s", (skill_code,))
            conn.execute("DELETE FROM skill_registry WHERE skill_id=%s", (skill_code,))
            conn.execute("DELETE FROM skill_plugin WHERE plugin_id=%s", (plugin_id,))


def test_postgres_marketplace_install_approval_contract() -> None:
    store = PostgresTaskStore(DATABASE_URL)
    store.init_full_schema()
    suffix = uuid4().hex
    package_id = f"pg-package-{suffix}"
    install_id = f"pg-install-{suffix}"
    try:
        saved = store.save_marketplace_install(
            {
                "install_id": install_id, "package_id": package_id, "name": "Contract package",
                "package_type": "skill", "version": "1.0.0", "source_url": "builtin://contract",
                "status": "previewed", "approval_status": "pending",
                "summary": {"files": 1}, "manifest": {"entry": "skill.json"},
            }
        )
        assert saved["approval_status"] == "pending"
        assert store.get_latest_marketplace_install(package_id)["summary"] == {"files": 1}
        assert any(row["install_id"] == install_id for row in store.list_marketplace_installs(package_type="skill"))
        approved = store.set_marketplace_approval(package_id, "approved", "contract-admin", "reviewed")
        assert approved["approval_status"] == "approved"
        assert approved["approved_by"] == "contract-admin"
    finally:
        with store.connection() as conn:
            conn.execute("DELETE FROM plugin_marketplace_install WHERE package_id=%s", (package_id,))
