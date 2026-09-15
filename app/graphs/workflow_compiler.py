from __future__ import annotations

from collections import defaultdict, deque
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.agents.code_review_tools import review_single_file
from app.graphs.project_analyzer_graph import project_analyzer_graph
from app.graphs.studio_graphs import code_review_graph, learning_coach_graph, rag_process_graph
from app.harness.events import utc_now_iso
from app.persistence.rag_store import rag_store
from app.providers.mcp_provider import mcp_provider
from app.skills.executor import execute_skill


# 这三个函数是 LangGraph 的状态更新策略。
# Annotated 类型告诉 LangGraph："这个字段更新时，用这个函数处理新旧值"。
# 列表追加（事件、工具调用累积）
def _append_list(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    return (left or []) + (right or [])

# 字典合并（审批记录合并）
def _merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    return {**(left or {}), **(right or {})}

# 取最新值（current、final_report 只保留最新的）
def _take_latest(left: Any, right: Any) -> Any:
    return right if right not in (None, "") else left

# 动态工作流的状态
class WorkflowState(TypedDict, total=False):
    workflow_name: str
    input_text: str
    goal: str
    project_path: str
    max_files: int
    require_human_review: bool
    task_id: str
    current: Annotated[str, _take_latest]   # 当前文本
    events: Annotated[list[dict[str, Any]], _append_list]  # 事件时间线
    outputs: Annotated[dict[str, Any], _merge_dict]  # 所有节点的产出
    tool_calls: Annotated[list[dict[str, Any]], _append_list] # 工具调用记录
    agent_outputs: Annotated[list[dict[str, Any]], _append_list]  # Agent 产出记录
    suggestions: Annotated[list[str], _append_list] # 建议列表
    human_review_packet: Annotated[dict[str, Any], _merge_dict] # 人工审核包
    human_approvals: Annotated[dict[str, Any], _merge_dict] # 审批记录
    review_retries: Annotated[dict[str, Any], _merge_dict] 
    resume_mode: bool  # 是否恢复模式
    review_action: str
    review_comment: str
    pause_workflow: Annotated[bool, _take_latest]  # 是否暂停
    final_report: Annotated[str, _take_latest]  # 最终报告
    mermaid: Annotated[str, _take_latest]
    validation: dict[str, Any]


SUPPORTED_NODE_TYPES = {"planner", "agent", "rag", "mcp_tool", "skill", "supervisor", "human_review", "reporter"}
SUPPORTED_EDGE_CONDITIONS = {"always", "on_status", "contains", "truthy_output"}
NODE_CONTRACTS: dict[str, dict[str, set[str]]] = {
    "planner": {"inputs": {"goal", "input_text"}, "outputs": {"steps", "plan", "text"}},
    "agent": {"inputs": {"goal", "input_text", "project_path"}, "outputs": {"text", "report_markdown", "findings"}},
    "rag": {"inputs": {"input_text", "question", "collection"}, "outputs": {"text", "results", "answer"}},
    "mcp_tool": {"inputs": {"input_text", "arguments"}, "outputs": {"text", "output", "status"}},
    "skill": {"inputs": {"input_text", "skill_input"}, "outputs": {"text", "output", "status"}},
    "supervisor": {"inputs": {"goal", "input_text"}, "outputs": {"text", "risk_level", "review_required"}},
    "human_review": {"inputs": {"input_text", "human_approvals"}, "outputs": {"status", "question", "output"}},
    "reporter": {"inputs": {"goal", "input_text", "outputs"}, "outputs": {"final_report", "text"}},
}
WORKFLOW_SCHEMA_VERSION = 1
NODE_INPUT_TYPES: dict[str, dict[str, str]] = {
    "planner": {"goal": "string", "input_text": "string", "project_path": "string"},
    "agent": {"goal": "string", "input_text": "string", "project_path": "string", "findings": "array"},
    "rag": {"input_text": "string", "question": "string", "collection": "string", "results": "array"},
    "mcp_tool": {"input_text": "string", "arguments": "object"},
    "skill": {"input_text": "string", "skill_input": "object"},
    "supervisor": {"goal": "string", "input_text": "string", "findings": "array"},
    "human_review": {"input_text": "string", "human_approvals": "object"},
    "reporter": {"goal": "string", "input_text": "string", "outputs": "object", "findings": "array"},
}
NODE_OUTPUT_TYPES: dict[str, dict[str, str]] = {
    "planner": {"steps": "array", "plan": "object", "text": "string"},
    "agent": {"text": "string", "report_markdown": "string", "findings": "array"},
    "rag": {"text": "string", "results": "array", "answer": "string"},
    "mcp_tool": {"text": "string", "output": "any", "status": "string"},
    "skill": {"text": "string", "output": "any", "status": "string"},
    "supervisor": {"text": "string", "risk_level": "string", "review_required": "boolean"},
    "human_review": {"status": "string", "question": "string", "output": "object"},
    "reporter": {"final_report": "string", "text": "string"},
}


# 输入：节点列表、边列表、入口节点 ID
# 输出：编译好的 LangGraph 图

# 流程：

# 标准化节点和边
# 验证工作流定义
# 创建 StateGraph，逐个添加节点
# 根据边定义连线
# 编译返回
def compile_workflow_graph(
    workflow_name: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    entry_node_id: str | None = None,
):
    normalized_nodes = _normalize_nodes(nodes)
    normalized_edges = _normalize_edges(normalized_nodes, edges or [])

    # 校验
    validation = validate_workflow_definition(normalized_nodes, normalized_edges)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    # 创建图
    graph = StateGraph(WorkflowState)
    
    # 逐个添加节点
    for node in normalized_nodes:
        graph.add_node(node["id"], _node_runner(node, normalized_nodes, normalized_edges))

    # 设置入口
    entry_id = entry_node_id or normalized_nodes[0]["id"]
    if entry_id not in {node["id"] for node in normalized_nodes}:
        raise ValueError(f"Workflow entry node `{entry_id}` does not exist.")
    graph.set_entry_point(entry_id)

    # 根据边连线
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in normalized_edges:
        outgoing[edge["source"]].append(edge)
    
    for node in normalized_nodes:
        source = node["id"]
        candidates = outgoing.get(source, [])
        if candidates:
            # 有条件边 → 用条件路由
            path_map = {edge["target"]: edge["target"] for edge in candidates}
            path_map["__end__"] = END
            graph.add_conditional_edges(source, _edge_router(source, candidates), path_map)
        else:
            # 无边 → 直接结束
            graph.add_edge(source, END)
    return graph.compile()

#  执行编译后的工作流

# 流程：
# 标准化、验证
# 编译图
# 构建初始状态
# 执行 graph.invoke(initial_state)
# 生成最终报告、Mermaid 流程图、恢复检查点
def run_compiled_workflow(
    workflow_name: str,
    input_text: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    extra_state: dict[str, Any] | None = None,
    entry_node_id: str | None = None,
) -> dict[str, Any]:
    # 1. 标准化
    normalized_nodes = _normalize_nodes(nodes)
    normalized_edges = _normalize_edges(normalized_nodes, edges or [])
    # 2. 校验
    validation = validate_workflow_definition(normalized_nodes, normalized_edges)
    # 3. 编译
    graph = compile_workflow_graph(workflow_name, normalized_nodes, normalized_edges, entry_node_id)
     # 4. 构建初始状态
    initial_state: dict[str, Any] = {
        "workflow_name": workflow_name,
        "input_text": input_text,
        "goal": input_text,
        "current": input_text,
        "events": [],
        "outputs": {},
        "tool_calls": [],
        "agent_outputs": [],
        "suggestions": [],
        "validation": validation,
    }
    # 如果是恢复模式，合并之前的现场
    if extra_state:
        initial_state.update({key: value for key, value in extra_state.items() if key != "events"})
        initial_state["events"] = []
        if extra_state.get("resume_mode"):
            initial_state["current"] = extra_state.get("current") or extra_state.get("input_text") or extra_state.get("goal") or input_text
            initial_state["pause_workflow"] = False
            initial_state["human_review_packet"] = {}
        else:
            initial_state["current"] = extra_state.get("input_text") or extra_state.get("goal") or input_text
    
    # 5. 运行
    result = graph.invoke(initial_state)

    # 6. 生成产物
    final_report = result.get("final_report") or _build_final_report(result)
    resume_checkpoint = _build_resume_checkpoint(
        workflow_name,
        input_text,
        normalized_nodes,
        normalized_edges,
        result,
        entry_node_id,
    )
    return {
        "workflow_name": workflow_name,
        "events": result.get("events", []),
        "output": result.get("current", ""),
        "final_report": final_report,
        "mermaid": result.get("mermaid") or _build_mermaid(_normalize_nodes(nodes), edges or []),
        "suggestions": result.get("suggestions", []),
        "tool_calls": result.get("tool_calls", []),
        "agent_outputs": result.get("agent_outputs", []),
        "human_review_packet": result.get("human_review_packet"),
        "validation": validation,
        "outputs": result.get("outputs", {}),
        "resume_checkpoint": resume_checkpoint,
    }

# 入口函数
# 从 Harness Runtime 传入的状态里提取参数，调 run_compiled_workflow()
# 然后把结果打包成统一格式返回。这是 Harness Runtime 调用的入口。
def run_task_workflow(input_state: dict[str, Any]) -> dict[str, Any]:
    workflow_name = input_state.get("workflow_name") or "visual_task_workflow"
    input_text = input_state.get("input_text") or input_state.get("goal") or ""
    nodes = input_state.get("nodes") or []
    edges = input_state.get("edges") or []
    result = run_compiled_workflow(workflow_name, input_text, nodes, edges, input_state)
    public_result = {
        "goal": input_state.get("goal") or input_text,
        "workflow_name": workflow_name,
        "final_report": result["final_report"],
        "mermaid": result["mermaid"],
        "suggestions": result["suggestions"],
        "suggestion_records": _collect_suggestion_records(result),
        "tool_calls": result["tool_calls"],
        "agent_outputs": result["agent_outputs"],
        **_governance_summary(result),
        "human_review_required": bool(result.get("human_review_packet")),
        "human_review_packet": result.get("human_review_packet"),
        "workflow_events": result["events"],
        "planned_workflow": input_state.get("planned_workflow"),
        "validation": result.get("validation", {}),
        "resume_checkpoint": result.get("resume_checkpoint"),
    }
    return {"result": public_result, "events": result["events"], "final_report": result["final_report"]}

# 断点恢复
def resume_task_workflow(checkpoint: dict[str, Any], action: str = "approved", comment: str | None = None) -> dict[str, Any]:
    workflow_name = str(checkpoint.get("workflow_name") or "visual_task_workflow")
    input_text = str(checkpoint.get("input_text") or checkpoint.get("goal") or "")
    paused_node_id = str(checkpoint.get("paused_node_id") or "") # 上次卡在哪个节点
    state = checkpoint.get("state") if isinstance(checkpoint.get("state"), dict) else {} # 上次的全部运行时状态
    
    # 把审批结果记录进去
    approvals = dict(state.get("human_approvals") or {})
    if paused_node_id:
        approvals[paused_node_id] = action # "approved" / "rejected"

    # 清除暂停节点的旧输出，让它重新执行
    # 暂停节点上次执行时生成的是 {"status": "pending", "question": "批准吗？"}。
    # 恢复后它要重新执行，生成 {"status": "approved"}。不删旧输出，字典里会有两个版本。
    outputs = dict(state.get("outputs") or {})
    paused_node = next((node for node in checkpoint.get("nodes", []) if isinstance(node, dict) and node.get("id") == paused_node_id), None)
    
    if paused_node:
        outputs.pop(_output_key(paused_node), None)
    
    # 构建恢复状态
    resume_state = {
        **state,
        "outputs": outputs,
        "resume_mode": True,
        "human_approvals": approvals, # 标记已审批
        "review_action": action,
        "review_comment": comment,  # 不含暂停节点的旧输出
    }

    # 从暂停节点重新跑
    # 恢复模式直接从暂停节点开始跑，前面的节点不重复执行。
    result = run_compiled_workflow(
        workflow_name,
        input_text,
        list(checkpoint.get("nodes") or []), # 完整的节点列表
        list(checkpoint.get("edges") or []), # 完整的边列表
        resume_state,
        paused_node_id, # ← 入口设为暂停节点
    )
    public_result = {
        "goal": checkpoint.get("goal") or state.get("goal") or input_text,
        "workflow_name": workflow_name,
        "final_report": result["final_report"],
        "mermaid": result["mermaid"],
        "suggestions": result["suggestions"],
        "suggestion_records": _collect_suggestion_records(result),
        "tool_calls": result["tool_calls"],
        "agent_outputs": result["agent_outputs"],
        **_governance_summary(result),
        "human_review_required": bool(result.get("human_review_packet")),
        "human_review_packet": result.get("human_review_packet"),
        "workflow_events": result["events"],
        "planned_workflow": checkpoint.get("planned_workflow"),
        "validation": result.get("validation", {}),
        "resume_checkpoint": result.get("resume_checkpoint"),
        "resumed_from": paused_node_id,
        "review_action": action,
    }
    return {"result": public_result, "events": result["events"], "final_report": result["final_report"]}


def _normalize_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [
        # 如果用户什么都没给，给一个默认的 4 节点流程
        {"id": "plan", "type": "planner", "name": "Task Planner", "config": {}},
        {"id": "analyze", "type": "agent", "name": "Project Agent", "config": {"agent_type": "project_analyzer"}},
        {"id": "review", "type": "human_review", "name": "Human Review", "config": {}},
        {"id": "report", "type": "reporter", "name": "Reporter", "config": {}},
    ] if not nodes else [{**node, "config": dict(node.get("config") or {})} for node in nodes]
    for node in normalized:
        config = node["config"]
        if "input_mappings" not in config and isinstance(config.get("input_mapping"), dict):
            config["input_mappings"] = config.pop("input_mapping")
    return normalized


def _normalize_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if edges:
        # 有边就用边，标准化格式
        return [
            {
                "source": str(edge.get("source") or ""),
                "target": str(edge.get("target") or ""),
                "condition": str(edge.get("condition") or "always"),
                "value": edge.get("value"),
                "source_path": str(edge.get("source_path") or ""),
            }
            for edge in edges
        ]
    # 没边就默认串行：节点0→节点1→节点2→...
    return [
        {"source": str(nodes[index]["id"]), "target": str(nodes[index + 1]["id"]), "condition": "always", "value": None, "source_path": ""}
        for index in range(len(nodes) - 1)
    ]

# 把当前工作流的所有状态打包保存，包括跑到了哪个节点、已有什么产出。
# 人工审批后，resume_task_workflow() 从这个包恢复现场。
def _build_resume_checkpoint(
    workflow_name: str,
    input_text: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    state: dict[str, Any],
    entry_node_id: str | None,
) -> dict[str, Any] | None:
    packet = state.get("human_review_packet")
    if not isinstance(packet, dict) or not packet:
        return None # 没暂停，不需要保存断点
    
    paused_node_id = str(packet.get("node_id") or "")

    if not paused_node_id:
        return None
    # 保存当前所有状态
    checkpoint_state = {
        "workflow_name": workflow_name,
        "input_text": input_text,
        "goal": state.get("goal") or input_text,
        "current": state.get("current") or input_text,
        "project_path": state.get("project_path"),
        "max_files": state.get("max_files"),
        "require_human_review": state.get("require_human_review"),
        "task_id": state.get("task_id"),
        "outputs": state.get("outputs", {}),
        "tool_calls": state.get("tool_calls", []),
        "agent_outputs": state.get("agent_outputs", []),
        "suggestions": state.get("suggestions", []),
        "review_retries": state.get("review_retries", {}),
        "validation": state.get("validation", {}),
    }
    return {
        "workflow_name": workflow_name,
        "input_text": input_text,
        "goal": checkpoint_state["goal"],
        "paused_node_id": paused_node_id,
        "entry_node_id": entry_node_id,
        "nodes": nodes,
        "edges": edges,
        "state": checkpoint_state,
        "created_at": utc_now_iso(),
    }

# 校验

# 跑之前检查 JSON 有没有问题。error 会阻断执行，warning 只是提醒。
# 检查项包括：节点类型是否合法、边是否连通、有没有死循环、有没有孤立节点。
def validate_workflow_definition(nodes: list[dict[str, Any]], edges: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized_nodes = _normalize_nodes(nodes)
    normalized_edges = _normalize_edges(normalized_nodes, edges or [])
    errors: list[str] = []
    warnings: list[str] = []
    node_ids = [str(node.get("id") or "") for node in normalized_nodes]
    node_id_set = set(node_ids)

    # 必须有节点
    if not normalized_nodes:
        errors.append("Workflow must contain at least one node.")
    if any(not node_id for node_id in node_ids):
        errors.append("Workflow node id cannot be empty.")
    if len(node_ids) != len(node_id_set):
        errors.append("Workflow node ids must be unique.")

    for node in normalized_nodes:
        if node.get("type") not in SUPPORTED_NODE_TYPES:
            errors.append(f"Unsupported node type `{node.get('type')}` in node `{node.get('id')}`.")
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        retry_count = config.get("retry_count", 0)
        if not isinstance(retry_count, int) or retry_count < 0 or retry_count > 5:
            errors.append(f"Node `{node.get('id')}` retry_count should be between 0 and 5.")
        if node.get("type") == "agent" and config.get("agent_type") == "file_reviewer" and not config.get("file_path"):
            warnings.append(f"File review node `{node.get('id')}` should set file_path.")
        if node.get("type") == "skill" and not config.get("skill_code"):
            errors.append(f"Skill node `{node.get('id')}` must set skill_code.")
        input_mapping = config.get("input_mapping")
        if input_mapping is not None and not isinstance(input_mapping, dict):
            errors.append(f"Node `{node.get('id')}` input_mapping must be an object.")
        output_schema = config.get("output_schema")
        if output_schema is not None and not isinstance(output_schema, dict):
            errors.append(f"Node `{node.get('id')}` output_schema must be an object.")
        input_schema = config.get("input_schema")
        if input_schema is not None and not isinstance(input_schema, dict):
            errors.append(f"Node `{node.get('id')}` input_schema must be an object.")
        if isinstance(input_schema, dict):
            errors.extend(_validate_contract_schema(node, input_schema, "input_schema"))
        if isinstance(output_schema, dict):
            errors.extend(_validate_contract_schema(node, output_schema, "output_schema"))

    _validate_cross_node_mappings(normalized_nodes, normalized_edges, errors, warnings)

    seen_edges: set[tuple[str, str, str]] = set()
    for edge in normalized_edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        condition = str(edge.get("condition") or "always")
        if source not in node_id_set:
            errors.append(f"Edge source `{source}` does not exist.")
        if target not in node_id_set:
            errors.append(f"Edge target `{target}` does not exist.")
        if condition not in SUPPORTED_EDGE_CONDITIONS:
            errors.append(f"Edge `{source}->{target}` uses unsupported condition `{condition}`.")
        marker = (source, target, condition)
        if marker in seen_edges:
            warnings.append(f"Duplicate edge `{source}->{target}` with condition `{condition}`.")
        seen_edges.add(marker)
        if condition in {"on_status", "contains"} and edge.get("value") in (None, ""):
            warnings.append(f"Conditional edge `{source}->{target}` should set value.")

    # 节点 ID 不能为空、不能重复
    # 节点类型必须在 SUPPORTED_NODE_TYPES 里
    # 边两端必须存在
    # 边条件必须在 SUPPORTED_EDGE_CONDITIONS 里
    

    # 检查是否有孤立节点（连不到的）
    reachable = _reachable_nodes(node_ids[0] if node_ids else "", normalized_edges)
    disconnected = sorted(node_id_set - reachable)
    if disconnected:
        errors.append(f"Disconnected node(s): {', '.join(disconnected)}.")
    if not any(node.get("type") == "reporter" for node in normalized_nodes):
        warnings.append("Workflow has no reporter node; final_report will be synthesized from node outputs.")
    
    # 检查是否有循环
    if _has_cycle(normalized_edges):
        errors.append("Workflow contains a cycle and cannot be compiled safely.")
    parallel_sources = sorted(source for source, count in _fan_out_counts(normalized_edges).items() if count > 1)
    if parallel_sources:
        warnings.append(f"Parallel fan-out detected at: {', '.join(parallel_sources)}.")

    return {
        "valid": not errors,
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(normalized_nodes),
        "edge_count": len(normalized_edges),
        "parallel_sources": parallel_sources,
    }


def _validate_cross_node_mappings(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], errors: list[str], warnings: list[str],
) -> None:
    by_id = {str(node.get("id")): node for node in nodes}
    output_owner: dict[str, dict[str, Any]] = {}
    for node in nodes:
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        output_owner[str(node["id"])] = node
        output_owner[str(config.get("output_key") or node["id"])] = node

    def source_type(source: str, path: str = "") -> str | None:
        token = source.strip()
        if token in {"current", "$current", "goal", "$goal", "input", "$input", "input_text", "$input_text"}:
            return "string"
        if token.startswith("outputs."):
            token = token.removeprefix("outputs.")
        parts = [part for part in token.split(".") if part]
        if not parts:
            return None
        owner = output_owner.get(parts[0])
        field = path.split(".", 1)[0] if path else (parts[1] if len(parts) > 1 else "")
        if not owner:
            return None
        config = owner.get("config") if isinstance(owner.get("config"), dict) else {}
        schema = config.get("output_schema") if isinstance(config.get("output_schema"), dict) else {}
        schema = schema or NODE_OUTPUT_TYPES.get(str(owner.get("type")), {})
        return schema.get(field) if field else "object"

    def check_mapping(node: dict[str, Any], target: str, source: str, path: str = "") -> None:
        node_type = str(node.get("type"))
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        input_schema = config.get("input_schema") if isinstance(config.get("input_schema"), dict) else {}
        target_type = input_schema.get(target) or NODE_INPUT_TYPES.get(node_type, {}).get(target)
        if target_type is None:
            errors.append(f"Node `{node.get('id')}` maps to unknown input field `{target}`.")
            return
        resolved = source_type(source, path)
        if resolved is None:
            errors.append(f"Node `{node.get('id')}` mapping source `{source}` does not resolve to a declared output.")
            return
        if resolved == "any" or target_type == "any":
            warnings.append(f"Node `{node.get('id')}` mapping `{source}` to `{target}` has an unknown runtime type.")
            return
        if resolved == "integer" and target_type == "number":
            return
        if resolved != target_type:
            errors.append(f"Node `{node.get('id')}` maps `{source}` ({resolved}) to `{target}` ({target_type}).")

    for node in nodes:
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        mappings = config.get("input_mappings")
        if isinstance(mappings, dict):
            for target, spec in mappings.items():
                if isinstance(spec, str):
                    check_mapping(node, str(target), spec)
                elif isinstance(spec, dict):
                    check_mapping(node, str(target), str(spec.get("source") or ""), str(spec.get("path") or ""))
                else:
                    errors.append(f"Node `{node.get('id')}` mapping for `{target}` must be a string or object.")
        input_from = config.get("input_from")
        if input_from:
            check_mapping(node, "input_text", str(input_from), str(config.get("input_path") or ""))
        if str(config.get("risk_level") or "").lower() in {"high", "critical"}:
            approval_nodes = [item for item in nodes if item.get("type") == "human_review"]
            protected = any(str(node.get("id")) in _reachable_nodes(str(review.get("id")), edges) for review in approval_nodes)
            if not protected:
                errors.append(f"High-risk node `{node.get('id')}` must be downstream of a human_review node.")

    for edge in edges:
        source_node = by_id.get(str(edge.get("source") or ""))
        if not source_node:
            continue
        source_path = str(edge.get("source_path") or "")
        condition = str(edge.get("condition") or "always")
        if not source_path:
            if condition in {"on_status", "contains"}:
                warnings.append(f"Conditional edge `{edge.get('source')}->{edge.get('target')}` has no source_path; runtime default will be used.")
            continue
        resolved = source_type(str(source_node.get("id")), source_path)
        if resolved is None:
            errors.append(f"Edge `{edge.get('source')}->{edge.get('target')}` references unknown output `{source_path}`.")
        elif condition == "on_status" and resolved != "string":
            errors.append(f"Edge `{edge.get('source')}->{edge.get('target')}` on_status source must be string, got {resolved}.")
        elif condition == "contains" and resolved not in {"string", "any"}:
            errors.append(f"Edge `{edge.get('source')}->{edge.get('target')}` contains source must be string, got {resolved}.")


def _validate_contract_schema(node: dict[str, Any], schema: dict[str, Any], field_name: str) -> list[str]:
    """Validate the portable field:type contract declared by a Workflow node."""
    allowed_types = {"string", "number", "integer", "boolean", "object", "array", "any"}
    errors: list[str] = []
    for field, field_type in schema.items():
        if not isinstance(field, str) or not field.strip():
            errors.append(f"Node `{node.get('id')}` {field_name} contains an empty field name.")
        if not isinstance(field_type, str) or field_type not in allowed_types:
            errors.append(f"Node `{node.get('id')}` {field_name}.{field} has unsupported type `{field_type}`.")
    return errors


def _validate_output_contract(output: Any, schema: dict[str, Any]) -> None:
    if not isinstance(output, dict):
        raise TypeError("Workflow node output must be an object when output_schema is declared")
    for field, expected in schema.items():
        if field not in output:
            raise ValueError(f"Workflow node output is missing required field `{field}`")
        value = output[field]
        if expected == "any":
            continue
        checks = {
            "string": isinstance(value, str), "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool), "boolean": isinstance(value, bool),
            "object": isinstance(value, dict), "array": isinstance(value, list),
        }
        if not checks.get(expected, False):
            raise TypeError(f"Workflow node output `{field}` must be {expected}")

# 节点包装器
# 1. 检查是否需要确认
# 2. 支持重试
# 3. 执行节点
# 4. 记录事件
# 5. 处理人工审核暂停
# 每个节点的统一包装器。
# 执行前检查确认、执行中支持重试、执行后记录事件、遇到人工审核就暂停。
def _node_runner(node: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]):
    def run(state: WorkflowState) -> WorkflowState:
        config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
        start_event = _event(state, node, "running", f"{_node_name(node)} started")
        outputs = dict(state.get("outputs", {}))

         # 1. 是否需要运行前确认
        if config.get("confirm_before_run") and not _confirmation_is_approved(state, node):
            packet = _confirmation_packet(node, state, outputs)
            return {
                "current": _compact_output(packet),
                "events": [start_event, _event(state, node, "waiting_review", packet["question"], {"output": packet})],
                "outputs": {_output_key(node): packet},
                "human_review_packet": packet,
                "pause_workflow": True,  # ← 暂停
            }
        # 2. 支持重试
        attempts = max(1, int(config.get("retry_count") or 0) + 1)
        retry_events: list[dict[str, Any]] = []
        try:
            for attempt in range(1, attempts + 1):
                try:
                    # 3. 输入映射
                    node_state = _state_with_mapped_input(state, node, outputs)
                    # 4. 真正执行
                    output, extra = _execute_node(node, node_state, outputs)
                    declared_output_schema = config.get("output_schema")
                    if isinstance(declared_output_schema, dict):
                        _validate_output_contract(output, declared_output_schema)
                    break
                except Exception as exc:
                    if attempt >= attempts:
                        raise
                    # 记录重试事件
                    retry_events.append(
                        _event(
                            state,
                            node,
                            "retrying",
                            f"{_node_name(node)} failed on attempt {attempt}: {exc}. Retrying.",
                            {"attempt": attempt, "max_attempts": attempts},
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - node boundary records and returns a failed node event
            update: WorkflowState = {
                "events": [start_event, *retry_events, _event(state, node, "failed", str(exc))],
                "outputs": {_output_key(node): {"error": str(exc), "status": "failed"}},
            }
            if config.get("fail_strategy", "halt") != "continue":
                update["pause_workflow"] = True
            return update

        current = _compact_output(output)
        status = "waiting_review" if node.get("type") == "human_review" and extra.get("human_review_packet") else "completed"
        update: WorkflowState = {
            "current": current,
            "events": [start_event, *retry_events, _event(state, node, status, current, {"output": output})],
            "outputs": {_output_key(node): output},
        }
        if extra.get("tool_call"):
            update["tool_calls"] = [extra["tool_call"]]
        if extra.get("agent_output"):
            update["agent_outputs"] = [extra["agent_output"]]
        if extra.get("suggestions"):
            update["suggestions"] = extra["suggestions"]
        if extra.get("human_review_packet"):
            update["human_review_packet"] = extra["human_review_packet"]
            if config.get("pause_on_review", node.get("type") == "human_review"):
                update["pause_workflow"] = True
        if node.get("type") == "reporter":
            update["final_report"] = current
            update["mermaid"] = _build_mermaid(nodes, edges)
        return update

    return run

#  条件路由
# 根据边的条件判断走哪条分支：

# always：总是走这条边
# on_status：根据节点执行状态判断
# contains：输出中包含特定内容时走这条边
# truthy_output：输出非空时走这条边
def _edge_router(source: str, edges: list[dict[str, Any]]):
    def route(state: WorkflowState) -> list[str]:
        if state.get("pause_workflow"):
            return ["__end__"] # 暂停就直接结束
        matched = [edge["target"] for edge in edges if _edge_matches(edge, state, source)]
        return matched or ["__end__"]

    return route

# 决定从一个节点出发走哪条分支。支持 4 种条件：总是走、按状态走、按内容走、按有无输出走。
def _edge_matches(edge: dict[str, Any], state: WorkflowState, source: str) -> bool:
    condition = str(edge.get("condition") or "always")
    if condition == "always":
        return True # 总是走这条边
    source_output = state.get("outputs", {}).get(source)
    value = str(edge.get("value") or "")
    if condition == "on_status":
        # 上一个节点执行状态匹配时走这条边
        latest = _latest_node_event(state, source)
        return str(latest.get("status") or "") == value
    if condition == "contains":
        # 上一个节点输出包含特定内容时走这条边
        haystack = _path_value(source_output, str(edge.get("source_path") or "")) if edge.get("source_path") else source_output
        return value.lower() in _condition_text(haystack).lower()
    if condition == "truthy_output":
        # 上一个节点有输出时走这条边
        target = _path_value(source_output, str(edge.get("source_path") or "")) if edge.get("source_path") else source_output
        return bool(target)
    return False


def _condition_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return str(value)
    return _compact_output(value)


def _latest_node_event(state: WorkflowState, node_id: str) -> dict[str, Any]:
    for event in reversed(state.get("events", [])):
        if event.get("node") == node_id or event.get("data", {}).get("node_id") == node_id:
            return event
    return {}

# 输入映射
# 一个节点可以指定 input_from: "code_reviewer"
# 意思是从代码审查节点的输出取数据作为自己的输入。
# 让节点 B 可以从节点 A 的输出取数据作为自己的输入,这实现了节点间的数据传递。
def _state_with_mapped_input(state: WorkflowState, node: dict[str, Any], outputs: dict[str, Any]) -> WorkflowState:
    config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
    input_from = str(config.get("input_from") or "").strip()
    if not input_from:
        return state
    if input_from in {"current", "$current"}:
        mapped = state.get("current")
    elif input_from in {"goal", "$goal"}:
        mapped = state.get("goal") or state.get("input_text")
    else:
        mapped = outputs.get(input_from)
    input_path = str(config.get("input_path") or "").strip()
    if input_path:
        mapped = _path_value(mapped, input_path)
    if mapped in (None, ""):
        return state
    text = _compact_output(mapped)
    return {**state, "goal": text, "input_text": text, "current": text}


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in [item for item in path.split(".") if item]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def _mapped_skill_input(config: dict[str, Any], state: WorkflowState, outputs: dict[str, Any]) -> dict[str, Any]:
    mappings = config.get("input_mappings")
    if not isinstance(mappings, dict):
        return {}
    mapped: dict[str, Any] = {}
    for target_key, source_spec in mappings.items():
        key = str(target_key or "").strip()
        if not key:
            continue
        if isinstance(source_spec, str):
            source = source_spec
            path = ""
        elif isinstance(source_spec, dict):
            source = str(source_spec.get("source") or "")
            path = str(source_spec.get("path") or "")
        else:
            continue
        value = _mapping_source_value(source, state, outputs)
        if path:
            value = _path_value(value, path)
        if value is not None:
            mapped[key] = value
    return mapped


def _mapping_source_value(source: str, state: WorkflowState, outputs: dict[str, Any]) -> Any:
    if source in {"current", "$current"}:
        return state.get("current")
    if source in {"goal", "$goal"}:
        return state.get("goal") or state.get("input_text")
    if source in {"input", "$input", "input_text", "$input_text"}:
        return state.get("input_text")
    if source.startswith("outputs."):
        return _path_value(outputs, source.removeprefix("outputs."))
    return outputs.get(source)


def _output_key(node: dict[str, Any]) -> str:
    config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
    return str(config.get("output_key") or node["id"])


def _confirmation_is_approved(state: WorkflowState, node: dict[str, Any]) -> bool:
    approvals = state.get("human_approvals")
    if isinstance(approvals, dict):
        return approvals.get(node["id"]) in {True, "approved", "approve"}
    return False


def _confirmation_packet(node: dict[str, Any], state: WorkflowState, outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending",
        "node_id": node["id"],
        "node_name": _node_name(node),
        "question": f"Approve running node `{_node_name(node)}`?",
        "options": ["approve", "reject", "revise"],
        "summary": _supervisor_notes(outputs) or [state.get("current") or state.get("goal") or ""],
    }


def _reachable_nodes(entry: str, edges: list[dict[str, Any]]) -> set[str]:
    if not entry:
        return set()
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[str(edge.get("source"))].append(str(edge.get("target")))
    seen = {entry}
    queue: deque[str] = deque([entry])
    while queue:
        node_id = queue.popleft()
        for target in outgoing.get(node_id, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _has_cycle(edges: list[dict[str, Any]]) -> bool:
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[str(edge.get("source"))].append(str(edge.get("target")))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in outgoing.get(node_id, []):
            if visit(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in list(outgoing))


def _fan_out_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        counts[str(edge.get("source"))] += 1
    return counts

# 节点执行分发器
# 整个文件最核心的函数：根据节点类型，调用不同的能力。
def _execute_node(node: dict[str, Any], state: WorkflowState, outputs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    node_type = node.get("type", "unknown")
    config = node.get("config", {})
    goal = state.get("goal") or state.get("input_text") or state.get("current") or ""
    project_path = state.get("project_path")
    max_files = int(config.get("max_files") or state.get("max_files") or 200)

    if node_type == "planner":
        # LLM 拆解任务
        plan = [
            "Read the task goal and choose an execution path.",
            "Run Agent, Tool, and Knowledge nodes according to canvas edges.",
            "Merge node outputs into a final report.",
        ]
        return {"plan": plan, "goal": goal}, {"agent_output": _agent_output(node, "planner", "\n".join(plan))}

    if node_type == "agent":
        return _run_agent_node(node, config, goal, project_path, max_files)

    if node_type == "rag":
        # 查询知识库
        collection = str(config.get("collection") or "default")
        limit = int(config.get("top_k") or 5)
        results = rag_store.query(collection, goal, limit)
        text = f"Knowledge collection {collection} returned {len(results)} result(s)."
        return {"collection": collection, "results": results}, {
            "agent_output": _agent_output(node, "rag", text),
            "suggestions": [text],
        }

    if node_type == "mcp_tool":
        return _run_tool_node(node, config, project_path, max_files)

    if node_type == "skill":
        skill_code = str(config.get("skill_code") or "")
        if not skill_code:
            raise ValueError("skill_code is required for skill node")
        skill_input = {
            "project_path": project_path,
            "root_path": project_path,
            "repo_path": project_path,
            "max_files": max_files,
            "goal": goal,
            **(config.get("input") if isinstance(config.get("input"), dict) else {}),
            **_mapped_skill_input(config, state, outputs),
        }
        result = execute_skill(
            skill_code,
            skill_input,
            agent_code=str(config.get("agent_code") or "skill_console"),
            task_id=str(state.get("task_id") or "") or None,
        )
        output = result.get("output", {})
        return output, {
            "agent_output": _agent_output(node, f"skill:{skill_code}", _compact_output(output)),
            "suggestions": [f"Skill `{skill_code}` completed in {result.get('latency_ms', 0)}ms."],
        }

    if node_type == "supervisor":
        # 汇总所有节点产出
        notes = _supervisor_notes(outputs)
        return {"notes": notes}, {"agent_output": _agent_output(node, "supervisor", "\n".join(notes))}

    if node_type == "human_review":
        # 检查是否已审批
        if _confirmation_is_approved(state, node):
            approved = {
                "status": "approved",
                "node_id": node["id"],
                "node_name": _node_name(node),
                "comment": state.get("review_comment"),
            }
            return approved, {"agent_output": _agent_output(node, "human_reviewer", "Human review approved.")}
        # 未审批 → 生成审核包
        packet = {
            "status": "pending",
            "node_id": node["id"],
            "node_name": _node_name(node),
            "question": "Approve archiving the current Workflow result?",
            "options": ["approve", "reject", "revise"],
            "summary": _supervisor_notes(outputs),
        }
        return packet, {"human_review_packet": packet}

    if node_type == "reporter":
        report = _build_final_report({**state, "outputs": outputs})
        return report, {"agent_output": _agent_output(node, "reporter", report)}

    text = f"{_node_name(node)} completed: {state.get('current') or goal}"
    return text, {"agent_output": _agent_output(node, node_type, text)}

# Agent 节点执行
# 特别的是 file_reviewer： review_single_file 没有被 Skill 包装，但在这里它被直接调用了。
# 动态工作流给了单文件审查一个使用入口。
def _run_agent_node(
    node: dict[str, Any],
    config: dict[str, Any],
    goal: str,
    project_path: str | None,
    max_files: int,
) -> tuple[Any, dict[str, Any]]:
    agent_type = str(config.get("agent_type") or config.get("agent") or "project_analyzer")
    if agent_type == "project_analyzer":
        if not project_path:
            raise ValueError("project_path is required for project_analyzer")
        result = project_analyzer_graph.invoke({"project_path": project_path, "max_files": max_files})
        text = result.get("report_markdown") or f"Project analysis completed: {result.get('quality_score', 'N/A')}"
    elif agent_type == "code_reviewer":
        if not project_path:
            raise ValueError("project_path is required for code_reviewer")
        result = code_review_graph.invoke({"project_path": project_path, "max_files": max_files})["result"]
        text = result.get("report_markdown") or f"Code review completed: {result.get('score', 'N/A')}"
    elif agent_type == "file_reviewer":
        if not project_path:
            raise ValueError("project_path is required for file_reviewer")
        file_path = str(config.get("file_path") or config.get("target_file") or "")
        if not file_path:
            raise ValueError("file_path is required for file_reviewer")
        result = review_single_file(
            project_path,
            file_path,
            int(config.get("max_chars") or 20000),
        )
        text = result.get("report_markdown") or f"File review completed: {result.get('file_path')}"
    elif agent_type == "rag_processor":
        if not project_path:
            raise ValueError("project_path is required for rag_processor")
        result = rag_process_graph.invoke({"project_path": project_path, "max_files": max_files})["result"]
        text = result.get("report_markdown") or f"RAG processing completed: {len(result.get('chunks', []))} chunks."
        should_ingest = bool(config.get("ingest", True))
        collection = str(config.get("collection") or "project-memory")
        if should_ingest:
            saved = rag_store.ingest(collection, result.get("documents", []), result.get("chunks", []))
            result = {
                **result,
                "ingest": {
                    "enabled": True,
                    "collection": collection,
                    **saved,
                },
            }
            text = (
                f"{text}\n\n"
                "## RAG 入库结果\n\n"
                f"- collection: `{collection}`\n"
                f"- documents: {saved['document_count']}\n"
                f"- chunks: {saved['chunk_count']}"
            )
        else:
            result = {**result, "ingest": {"enabled": False, "collection": collection}}
    elif agent_type == "learning_coach":
        result = learning_coach_graph.invoke(
            {
                "topic": config.get("topic") or goal or "LangGraph",
                "level": config.get("level") or "beginner",
                "days": int(config.get("days") or 7),
            }
        )["result"]
        text = result.get("report_markdown") or "Learning plan generated."
    else:
        result = {"message": f"Unknown Agent: {agent_type}", "goal": goal}
        text = result["message"]
    focus = config.get("focus")
    output_format = config.get("output_format")
    if isinstance(result, dict) and (focus or output_format):
        result = {
            **result,
            "user_focus": focus,
            "output_format": output_format,
        }
        text = f"{text}\n\nUser focus: {focus or 'not specified'}\nOutput format: {output_format or 'default'}"
    extra: dict[str, Any] = {"agent_output": _agent_output(node, agent_type, text)}
    if agent_type == "rag_processor":
        ingest = result.get("ingest") if isinstance(result, dict) else None
        if isinstance(ingest, dict) and ingest.get("enabled"):
            extra["suggestions"] = [
                f"RAG chunks ingested into `{ingest.get('collection')}`: {ingest.get('chunk_count', 0)} chunk(s)."
            ]
    return result, extra


def _run_tool_node(
    node: dict[str, Any],
    config: dict[str, Any],
    project_path: str | None,
    max_files: int,
) -> tuple[Any, dict[str, Any]]:
    tool_name = str(config.get("tool_name") or "filesystem.list")
    root_path = str(config.get("root_path") or project_path or ".")
    arguments = {
        "root_path": root_path,
        "repo_path": root_path,
        "max_files": int(config.get("max_files") or max_files),
        "file_path": str(config.get("file_path") or "README.md"),
        "max_chars": int(config.get("max_chars") or 4000),
        "limit": int(config.get("limit") or 10),
        **(config.get("arguments") if isinstance(config.get("arguments"), dict) else {}),
    }
    result = mcp_provider.call_tool(
        tool_name,
        arguments,
        server_id=str(config.get("server_id") or "") or None,
        agent_code=str(config.get("agent_code") or "workflow_runner"),
    )
    tool_call = {"node_id": node["id"], "tool_name": tool_name, "status": "completed", "result": result}
    return result, {"tool_call": tool_call, "agent_output": _agent_output(node, tool_name, f"Tool {tool_name} completed.")}


def _event(
    state: WorkflowState,
    node: dict[str, Any],
    status: str,
    content: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = state.get("task_id") or "workflow_preview"
    return {
        "task_id": task_id,
        "event_id": f"evt_{task_id}_{node['id']}_{uuid4().hex[:8]}",
        "type": "workflow_node",
        "node": node["id"],
        "agent": node.get("type", "workflow"),
        "status": status,
        "content": content,
        "timestamp": utc_now_iso(),
        "data": {
            "node_id": node["id"],
            "node_type": node.get("type"),
            "node_name": _node_name(node),
            **(data or {}),
        },
    }


def _agent_output(node: dict[str, Any], agent: str, content: str) -> dict[str, str]:
    return {"node_id": node["id"], "node_name": _node_name(node), "agent": agent, "content": content}


def _node_name(node: dict[str, Any]) -> str:
    return str(node.get("name") or node["id"])


def _compact_output(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        if "report_markdown" in output:
            return str(output["report_markdown"])
        if "message" in output:
            return str(output["message"])
        if "plan" in output:
            return "\n".join(f"- {item}" for item in output["plan"])
        if "notes" in output:
            return "\n".join(f"- {item}" for item in output["notes"])
    return str(output)


def _supervisor_notes(outputs: dict[str, Any]) -> list[str]:
    notes = [f"Merged {len(outputs)} node output(s)."]
    for node_id, output in outputs.items():
        text = _compact_output(output).replace("\n", " ")
        notes.append(f"{node_id}: {text[:120]}")
    return notes


def _build_final_report(state: dict[str, Any]) -> str:
    goal = state.get("goal") or state.get("input_text") or "Untitled task"
    outputs = state.get("outputs", {})
    agent_outputs = state.get("agent_outputs", [])
    tool_calls = state.get("tool_calls", [])
    suggestions = state.get("suggestions", [])

    lines = [
        "# Workflow Execution Report",
        "",
        "## Goal",
        "",
        str(goal),
        "",
        "## Agent Outputs",
        "",
    ]
    if agent_outputs:
        for item in agent_outputs:
            first_line = str(item.get("content", "")).splitlines()[0][:180]
            lines.append(f"- **{item.get('node_name')} / {item.get('agent')}**: {first_line}")
    else:
        lines.append("- No Agent output.")

    lines.extend(["", "## Tool Calls", ""])
    if tool_calls:
        for item in tool_calls:
            lines.append(f"- **{item.get('tool_name')}**: {item.get('status')}")
    else:
        lines.append("- No tool call.")

    lines.extend(["", "## Node Result Summary", ""])
    for node_id, output in outputs.items():
        lines.append(f"- **{node_id}**: {_compact_output(output).splitlines()[0][:180]}")

    detailed_reports = [
        (node_id, str(output["report_markdown"]))
        for node_id, output in outputs.items()
        if isinstance(output, dict) and output.get("report_markdown")
    ]
    if detailed_reports:
        lines.extend(["", "## Detailed Agent Reports", ""])
        for node_id, report in detailed_reports:
            lines.extend([f"### {node_id}", "", report, ""])

    lines.extend(["", "## Suggestions", ""])
    if suggestions:
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")
    else:
        lines.extend(
            [
                "- Save high-frequency workflows as reusable templates.",
                "- Add human review to high-risk nodes.",
                "- Upgrade RAG nodes to vector retrieval and MCP nodes to a real MCP client later.",
            ]
        )
    return "\n".join(lines)


def _governance_summary(result: dict[str, Any]) -> dict[str, Any]:
    records = _collect_suggestion_records(result)
    suggestions = [str(item) for item in result.get("suggestions", [])]
    outputs = result.get("outputs", {})
    review_required = bool(result.get("human_review_packet")) or any(record.get("review_required") for record in records)
    risk_level = _highest_risk([record.get("risk_level") for record in records])
    if risk_level == "low" and _report_mentions_risk(outputs):
        risk_level = "medium"
    if risk_level in {"high", "critical"} and _contains_fallback(outputs):
        review_required = True
    next_actions = _collect_next_actions(records, suggestions)
    return {
        "risk_level": risk_level,
        "review_required": review_required,
        "next_actions": next_actions,
        "governance": {
            "risk_level": risk_level,
            "review_required": review_required,
            "next_actions": next_actions,
            "suggestion_record_count": len(records),
        },
    }


def _collect_suggestion_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for output in result.get("outputs", {}).values():
        if isinstance(output, dict):
            records.extend(item for item in output.get("suggestion_records", []) if isinstance(item, dict))
    return records


def _highest_risk(values: list[Any]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    level = "low"
    for value in values:
        key = str(value or "low")
        if order.get(key, 0) > order[level]:
            level = key
    return level


def _contains_fallback(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("fallback_used") is True or value.get("answer_source") in {"fallback", "rule"}:
            return True
        return any(_contains_fallback(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_fallback(item) for item in value)
    return False


def _collect_next_actions(records: list[dict[str, Any]], suggestions: list[str]) -> list[str]:
    actions: list[str] = []
    for record in records:
        for action in record.get("next_actions", [])[:2]:
            if action not in actions:
                actions.append(str(action))
    for suggestion in suggestions[:5]:
        if suggestion not in actions:
            actions.append(suggestion)
    return actions[:6] or [
        "Review the generated report.",
        "Save useful conclusions to project-memory.",
        "Add regression tests for the highest-risk workflow.",
    ]


def _report_mentions_risk(outputs: dict[str, Any]) -> bool:
    text = "\n".join(str(output.get("report_markdown", output)) for output in outputs.values() if isinstance(output, dict))
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["risk", "风险", "security", "critical", "high"])


def _build_mermaid(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> str:
    normalized_nodes = _normalize_nodes(nodes)
    lines = ["flowchart LR"]
    for node in normalized_nodes:
        lines.append(f"  {node['id']}[{_node_name(node)}]")
    for edge in edges:
        label = ""
        if edge.get("condition") and edge.get("condition") != "always":
            suffix = f": {edge.get('value')}" if edge.get("value") not in (None, "") else ""
            label = f"|{edge.get('condition')}{suffix}|"
        lines.append(f"  {edge['source']} -->{label} {edge['target']}")
    if not edges:
        for index, node in enumerate(normalized_nodes[:-1]):
            lines.append(f"  {node['id']} --> {normalized_nodes[index + 1]['id']}")
    return "\n".join(lines)
