"""Strict SQLite-to-PostgreSQL mapping used only by the rehearsal migration CLI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

MAPPING_VERSION = "sqlite-to-postgres-v2"

# These are all current persistence tables. A source table not in this list is
# intentionally a migration blocker: silently dropping data is never valid.
MIGRATION_TABLES = (
    "agent_task",
    "agent_worker",
    "agent_task_event",
    "agent_task_artifact",
    "agent_task_node_state",
    "workflow_definition",
    "human_review_action",
    "learning_plan",
    "llm_call_trace",
    "llm_prompt_version",
    "mcp_server_config",
    "mcp_tool_registry",
    "mcp_tool_approval",
    "mcp_tool_call_log",
    "benchmark_run",
    "benchmark_result",
    "benchmark_comparison",
    "skill_plugin",
    "skill_registry",
    "skill_approval",
    "skill_execution_log",
    "skill_version_snapshot",
    "plugin_marketplace_install",
    "marketplace_install_snapshot",
    "platform_approval",
    "platform_query",
    "platform_version",
    "security_audit_log",
    "memory_record",
    "memory_lifecycle_event",
    "rag_document",
    "rag_chunk",
    "rag_gold_case",
    "rag_evaluation_run",
    "schema_migration",
)


@dataclass(frozen=True)
class TableMapping:
    source_table: str
    target_table: str
    aliases: Mapping[str, str]
    generated_target_columns: frozenset[str] = frozenset()
    ignored_source_columns: frozenset[str] = frozenset({"id"})
    # Values generated solely for the PostgreSQL representation are written
    # during import but must not participate in source-data verification.
    verification_excluded_target_columns: frozenset[str] = frozenset()


_DEFAULT = TableMapping(source_table="", target_table="", aliases={})

TABLE_MAPPINGS: dict[str, TableMapping] = {
    name: TableMapping(name, name, {}) for name in MIGRATION_TABLES
}
TABLE_MAPPINGS.update(
    {
        "agent_task_event": TableMapping(
            "agent_task_event", "agent_task_event", {}, frozenset(), frozenset({"id"})
        ),
        "agent_task_artifact": TableMapping(
            "agent_task_artifact", "agent_task_artifact", {}, frozenset({"id"}), frozenset({"id"})
        ),
        "human_review_action": TableMapping(
            "human_review_action", "human_review_action", {}, frozenset(), frozenset({"id"})
        ),
        "llm_call_trace": TableMapping(
            "llm_call_trace", "llm_call_trace", {}, frozenset(), frozenset({"id"})
        ),
        "llm_prompt_version": TableMapping(
            "llm_prompt_version", "llm_prompt_version", {}, frozenset(), frozenset({"id"})
        ),
        "mcp_tool_registry": TableMapping(
            "mcp_tool_registry",
            "mcp_tool_registry",
            {"tool_name": "name", "input_schema": "input_schema_json"},
        ),
        "mcp_tool_approval": TableMapping(
            "mcp_tool_approval", "mcp_tool_approval", {}, frozenset(), frozenset({"id"})
        ),
        "benchmark_result": TableMapping(
            "benchmark_result", "benchmark_result", {}, frozenset(), frozenset({"id"})
        ),
        "skill_registry": TableMapping(
            "skill_registry", "skill_registry", {"skill_id": "skill_code"}
        ),
        "skill_approval": TableMapping(
            "skill_approval", "skill_approval", {}, frozenset(), frozenset({"id"})
        ),
        "skill_version_snapshot": TableMapping(
            "skill_version_snapshot", "skill_version_snapshot", {}, frozenset({"id"}), frozenset({"id"})
        ),
        "rag_document": TableMapping(
            "rag_document", "rag_document", {}, frozenset({"id"}), frozenset({"id"})
        ),
        "rag_chunk": TableMapping(
            "rag_chunk",
            "rag_chunk",
            {},
            frozenset({"id"}),
            frozenset({"id"}),
            frozenset({"embedding", "embedding_source"}),
        ),
    }
)
