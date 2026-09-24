from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.observability import record_domain_operation, stable_error_code
from app.core.security import execution_auth_context
from app.harness.events import utc_now_iso
from app.persistence.factory import get_persistence_stores
from app.providers.llm_provider import llm_provider
from app.skills.base import SkillContext
from app.skills.builtin import builtin_plugin
from app.skills.contract import validate_skill_contract
from app.skills.registry import skill_registry
from app.skills.sandbox import python_skill_sandbox_status, run_python_skill_sandbox


# 先把内置 Skill 写入数据库，保证外部能查到
# 光有内存里的 skill_registry 还不够
# 前端页面、审批管理、版本管理、执行日志这些功能都需要数据库里有 Skill 记录。
def ensure_builtin_skills_seeded() -> None:
    get_persistence_stores().skill.seed_builtin_skills(builtin_plugin(), skill_registry.list_skills())


# 查数据库中的 Skill
# - 检查启用状态
# - 检查审批
# - 校验合约
# - 检查依赖
# - 合并默认输入和外部输入
# - 执行并写日志

# skill_code：要执行哪个 Skill，比如 code.review
# input_data：这次执行的输入
# agent_code：谁在调用它，比如 skill_console 或 workflow_runner
# task_id：可选，关联到某个任务
def execute_skill(
    skill_code: str,
    input_data: dict[str, Any] | None = None,
    *,
    agent_code: str = "skill_console",
    task_id: str | None = None,
) -> dict[str, Any]:
    ensure_builtin_skills_seeded()

    # 不是 registry 里有就能用
    # 必须数据库里也有记录
    skill = get_persistence_stores().skill.get_skill(skill_code)
    if not skill:
        raise KeyError(f"Skill not found: {skill_code}")
    # Skill 即使存在，也可能被管理员禁用
    if not skill.get("enabled"):
        raise PermissionError(f"Skill disabled: {skill_code}")
    permissions = skill.get("permissions") if isinstance(skill.get("permissions"), list) else []
    # 如果 Skill 带有权限要求，而当前 agent_code 没审批，就不能执行
    approval = get_persistence_stores().skill.get_skill_approval(skill_code, agent_code)
    if permissions and not (approval and approval.get("allowed")):
        raise PermissionError(f"Skill `{skill_code}` is not approved for agent `{agent_code}`.")
    
    # 先检查定义是不是规范
    contract = validate_skill_contract(skill)
    if not contract["valid"]:
        raise ValueError(f"Skill contract invalid: {'; '.join(contract['errors'])}")
    # 检查依赖
    missing_dependencies = _missing_dependencies(skill)
    if missing_dependencies:
        raise RuntimeError(f"Skill dependencies are missing: {', '.join(missing_dependencies)}")

    # 合并默认输入和外部输入
    # Skill 自己可以带默认参数,调用方传进来的参数会覆盖默认值
    payload = {**(skill.get("default_input") or {}), **(input_data or {})}

    # 生成日志 ID 并开始计时
    log_id = f"skill_log_{uuid4().hex}"
    started = time.perf_counter()
    auth_context = execution_auth_context()
    # 这里分两条路真正执行 Skill
    try:
        # 路线 A：注册在 registry 里的内置 Skill
        try:
            output = skill_registry.execute(
                skill_code,
                SkillContext(task_id=task_id, agent_code=agent_code, variables={}),
                payload,
            )
        except KeyError:
            # 路线 B：没注册到 registry 的声明式 Skill
            output = _execute_declarative_skill(skill, payload)
        latency_ms = int((time.perf_counter() - started) * 1000)
        get_persistence_stores().skill.save_skill_execution_log(
            {
                "log_id": log_id,
                "skill_code": skill_code,
                "agent_code": agent_code,
                "task_id": task_id,
                "input": payload,
                "output": output,
                "status": "completed",
                "latency_ms": latency_ms,
                "request_id": auth_context.request_id,
                "actor_id": auth_context.actor_id,
                "role": auth_context.role,
                "created_at": utc_now_iso(),
            }
        )
        record_domain_operation("skill", "execute", started, status="success")
        return {
            "log_id": log_id,
            "skill": skill,
            "input": payload,
            "output": output,
            "status": "completed",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        # 保存成功日志,这让 Skill 执行是可审计的，不是黑盒
        get_persistence_stores().skill.save_skill_execution_log(
            {
                "log_id": log_id,
                "skill_code": skill_code,
                "agent_code": agent_code,
                "task_id": task_id,
                "input": payload,
                "output": {},
                "status": "failed",
                "error_message": str(exc),
                "latency_ms": latency_ms,
                "request_id": auth_context.request_id,
                "actor_id": auth_context.actor_id,
                "role": auth_context.role,
                "created_at": utc_now_iso(),
            }
        )
        record_domain_operation("skill", "execute", started, status="failed", error_code=stable_error_code(exc))
        raise

# 给“声明式 Skill”用的
def _execute_declarative_skill(skill: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    execution_type = str(skill.get("execution_type") or "prompt")
    # 这类 Skill 的特点
    # 是外部 Python 文件
    # 要在隔离环境里跑
    # 不能直接随便执行
    if execution_type == "python":
        default_input = skill.get("default_input") if isinstance(skill.get("default_input"), dict) else {}
        entrypoint_path = str(default_input.get("_entrypoint_path") or skill.get("entrypoint") or "")
        function_name = str(default_input.get("_entrypoint_function") or "run")
        timeout_seconds = int(default_input.get("_timeout_seconds") or 10)
        sandbox_status = python_skill_sandbox_status()
        is_external = str(skill.get("source_plugin") or "") != builtin_plugin().get("plugin_id")
        if settings.jaycode_external_skill_require_docker and is_external and sandbox_status.get("mode") != "docker":
            raise PermissionError("External Python Skills require Docker sandbox execution")
        if is_external and sandbox_status.get("mode") == "docker" and sandbox_status.get("fallback_enabled"):
            raise PermissionError("External Python Skills cannot fall back from Docker sandbox")
        output = run_python_skill_sandbox(entrypoint_path, function_name, payload, timeout_seconds=timeout_seconds)
        return {
            **output,
            "_sandbox": {
                **sandbox_status,
                "timeout_seconds": timeout_seconds,
                "entrypoint": entrypoint_path,
                "third_party_code_executed": True,
            },
        }
    # 本质上是一个 Prompt 技能
    # 不执行代码
    # 通过 LLM 生成 Markdown 报告
    if execution_type == "prompt":
        template = str((skill.get("default_input") or {}).get("_prompt_template") or skill.get("description") or skill.get("name") or "")
        user_prompt = _render_template(template, payload)
        fallback = (
            f"# {skill.get('name')}\n\n"
            f"Declarative prompt skill executed.\n\n"
            f"## Input\n\n```json\n{payload}\n```"
        )
        text = llm_provider.generate(
            "You are a Jaycode marketplace skill. Return a concise Markdown report based only on the provided input.",
            user_prompt,
            fallback,
            agent=f"skill:{skill.get('code')}",
            prompt_version=f"{skill.get('code')}.marketplace.v1",
        )
        return {"report_markdown": text, "answer_source": "llm" if llm_provider.enabled else "fallback"}
    # 不靠 LLM
    # 不跑外部代码
    # 适合固定、可控、轻量的能力
    if execution_type == "rule":
        return {
            "report_markdown": f"# {skill.get('name')}\n\nRule skill registered from marketplace.\n\nInput keys: {', '.join(payload.keys())}",
            "input": payload,
        }
    return {
        "report_markdown": f"# {skill.get('name')}\n\nDeclarative skill type `{execution_type}` is registered. Custom execution is not enabled.",
        "input": payload,
    }


def _render_template(template: str, payload: dict[str, Any]) -> str:
    rendered = template
    for key, value in payload.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered

# 如果 Skill 声明了依赖，比如：
# 某个 MCP 工具
# 某个 RAG collection
# 某个 prompt 版本
# 某个别的 Skill
# 某个 LLM 模型
# 这里就会逐个检查。
def _missing_dependencies(skill: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    dependencies = skill.get("dependencies") if isinstance(skill.get("dependencies"), list) else []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        dep_type = str(dependency.get("type") or "")
        dep_ref = str(dependency.get("ref") or dependency.get("name") or "")
        if not dep_ref:
            continue
        if dep_type == "mcp_tool":
            if ":" in dep_ref:
                server_id, tool_name = dep_ref.split(":", 1)
                found = get_persistence_stores().mcp.get_mcp_tool(server_id, tool_name)
            else:
                found = any(tool.get("name") == dep_ref for tool in get_persistence_stores().mcp.list_mcp_tools())
            if not found:
                missing.append(f"mcp_tool:{dep_ref}")
        elif dep_type == "rag_collection":
            if not get_persistence_stores().rag.list_documents(dep_ref):
                missing.append(f"rag_collection:{dep_ref}")
        elif dep_type == "prompt_version":
            agent = str(dependency.get("agent") or "reporter")
            if not get_persistence_stores().prompt.get_prompt_version(agent, dep_ref):
                missing.append(f"prompt_version:{agent}/{dep_ref}")
        elif dep_type == "skill":
            if not get_persistence_stores().skill.get_skill(dep_ref):
                missing.append(f"skill:{dep_ref}")
        elif dep_type == "llm_model":
            if not llm_provider.enabled:
                missing.append(f"llm_model:{dep_ref}")
    return missing
