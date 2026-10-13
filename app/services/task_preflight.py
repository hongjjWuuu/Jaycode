from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.project_paths import ProjectPathError, ResolvedProject, resolve_project_path
from app.persistence.factory import get_persistence_stores

PROJECT_AGENTS = {"project_analyzer", "code_reviewer", "file_reviewer", "rag_processor"}
PROJECT_INPUT_KEYS = {"project_path", "root_path", "repo_path"}
PROJECT_MCP_TOOLS = {"read_file", "write_file", "list_directory", "directory_tree", "search_files", "git_status", "git_log"}


@dataclass(frozen=True)
class TaskPreflight:
    project: ResolvedProject | None
    requires_project: bool
    project_reasons: tuple[str, ...]


def _knowledge_scope(node: dict[str, Any]) -> str:
    config = node.get("config") if isinstance(node.get("config"), dict) else {}
    return str(config.get("knowledge_scope") or "").strip()


def _is_knowledge_node(node: dict[str, Any]) -> bool:
    config = node.get("config") if isinstance(node.get("config"), dict) else {}
    return node.get("type") == "rag" or (
        node.get("type") == "agent" and str(config.get("agent_type") or config.get("agent")) == "rag_processor"
    )


def inspect_workflow_dependencies(nodes: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "unknown")
        node_type = str(node.get("type") or "")
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        if _is_knowledge_node(node):
            scope = _knowledge_scope(node)
            if not scope:
                raise ProjectPathError(
                    "KNOWLEDGE_SCOPE_REQUIRED",
                    "知识节点必须明确选择“当前项目知识”“历史共享知识”或“自定义集合”并重新保存流程。",
                    node_id=node_id,
                )
            if scope not in {"project", "legacy_shared", "custom"}:
                raise ProjectPathError("KNOWLEDGE_SCOPE_REQUIRED", "知识节点的知识范围无效。", node_id=node_id)
            if scope == "custom" and not str(config.get("collection") or "").strip():
                raise ProjectPathError("KNOWLEDGE_SCOPE_REQUIRED", "自定义知识范围必须指定 collection。", node_id=node_id)
            if scope == "project":
                reasons.append(f"知识节点 {node_id} 使用当前项目知识")
        if node_type == "agent" and str(config.get("agent_type") or config.get("agent") or "project_analyzer") in PROJECT_AGENTS:
            reasons.append(f"Agent 节点 {node_id} 需要读取项目")
        elif node_type == "mcp_tool":
            tool_name = str(config.get("tool_name") or "")
            if tool_name.startswith(("filesystem.", "git.")) or tool_name.lower() in PROJECT_MCP_TOOLS:
                reasons.append(f"工具节点 {node_id} 需要访问文件或 Git")
        elif node_type == "skill":
            skill = get_persistence_stores().skill.get_skill(str(config.get("skill_code") or ""))
            schema = skill.get("input_schema") if isinstance(skill, dict) else config.get("input_schema")
            if isinstance(schema, dict) and PROJECT_INPUT_KEYS.intersection(schema):
                reasons.append(f"Skill 节点 {node_id} 需要项目路径")
            else:
                skill_input = config.get("input") if isinstance(config.get("input"), dict) else {}
                if PROJECT_INPUT_KEYS.intersection(skill_input):
                    reasons.append(f"Skill 节点 {node_id} 需要项目路径")
    return bool(reasons), list(dict.fromkeys(reasons))


def preflight_task(nodes: list[dict[str, Any]], project_path: str | None) -> TaskPreflight:
    requires_project, reasons = inspect_workflow_dependencies(nodes)
    if requires_project and not (project_path or "").strip():
        raise ProjectPathError(
            "PROJECT_PATH_REQUIRED",
            "当前流程会扫描本地项目，请先填写并验证项目路径。",
            project_reasons=reasons,
        )
    project = resolve_project_path(project_path) if (project_path or "").strip() else None
    return TaskPreflight(project, requires_project, tuple(reasons))
