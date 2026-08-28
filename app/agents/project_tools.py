from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.providers.llm_provider import llm_provider

# 扫描时跳过这些目录。
# 这些东西要么是依赖、要么是构建产物、要么是 IDE 配置
# 对理解项目结构没有帮助，扫了反而干扰判断。
EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "build",
    "dist",
    "__pycache__",
}

# 定义"关键文件"白名单。
# 这些文件能直接告诉我们项目用什么技术栈、怎么构建、怎么部署。
# 后面识别技术栈、判断项目健康状况都靠它们。
KEY_FILE_NAMES = {
    "README.md",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "application.yml",
    "application.yaml",
    "application.properties",
    "tsconfig.json",
    "vite.config.ts",
    "rsbuild.config.ts",
}

# 输入：项目路径、最大扫描文件数
# 输出：一个字典，包含项目名、所有文件列表、所有目录列表、关键文件列表
def scan_project(project_path: str, max_files: int) -> dict[str, Any]:
    
    # 用 Path.rglob("*") 递归遍历所有文件和目录
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    files: list[dict[str, Any]] = []
    directories: set[str] = set()
    key_files: list[str] = []

    for path in root.rglob("*"):

        # 跳过 EXCLUDED_DIRS 中的目录
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.add(rel)
            continue
        # 文件数量达到 max_files 时停止（防止超大项目扫太久）
        if len(files) >= max_files:
            break
        suffix = path.suffix.lower()

        # 对每个文件记录：路径、名字、后缀、大小
        item = {
            "path": rel,
            "name": path.name,
            "suffix": suffix,
            "size": path.stat().st_size,
        }
        files.append(item)

        # 判断是否在 KEY_FILE_NAMES 中，是则加入关键文件列表
        if path.name in KEY_FILE_NAMES or path.name.lower().startswith("readme"):
            key_files.append(rel)

    return {
        "root": root.as_posix(),
        "project_name": root.name,
        "files": files,
        "directories": sorted(directories),
        "key_files": sorted(key_files),
    }

# 根据文件名、后缀、路径推断技术栈
# 输入：scan_project() 的返回结果
# 输出：技术栈列表，如 ["Python", "FastAPI", "Docker", "PostgreSQL"]
def identify_tech_stack(scan: dict[str, Any]) -> list[str]:
    paths = {file["path"] for file in scan["files"]}
    names = {file["name"] for file in scan["files"]}
    suffixes = {file["suffix"] for file in scan["files"]}
    stack: set[str] = set()

    # 核心逻辑：用一系列 if 判断来"猜"技术栈：
    # 有 pom.xml → Java + Maven
    # 有 package.json → Node.js + 前端
    # 有 pyproject.toml → Python
    # 文件名包含 controller → 可能是 Spring Boot
    # 目录名包含 mcp → 用了 MCP 协议
    # 目录名包含 rag → 用了 RAG
    # 这是"基于信号的特征识别"，不是 AI 推理，是规则匹配。
    # 优点是快、准、零成本，缺点是无法发现"没有预定义信号"的技术。
    # 所以后面报告里还会让 LLM 补充。
    if "pom.xml" in names:
        stack.update({"Java", "Maven"})
    if "build.gradle" in names or "settings.gradle" in names:
        stack.update({"Java", "Gradle"})
    if any(path.endswith("Application.java") for path in paths):
        stack.add("Spring Boot")
    if any("mybatis" in path.lower() for path in paths):
        stack.add("MyBatis")
    if "package.json" in names:
        stack.update({"Node.js", "Frontend"})
    if "tsconfig.json" in names or ".tsx" in suffixes or ".ts" in suffixes:
        stack.add("TypeScript")
    if ".tsx" in suffixes or any("react" in path.lower() for path in paths):
        stack.add("React")
    if "pyproject.toml" in names or "requirements.txt" in names:
        stack.add("Python")
    if any(path.endswith("main.py") for path in paths):
        stack.add("FastAPI/Python Service")
    if "Dockerfile" in names or "docker-compose.yml" in names:
        stack.add("Docker")
    if any(path.endswith(".sql") for path in paths):
        stack.add("SQL")
    if any("mcp" in path.lower() for path in paths):
        stack.add("MCP")
    if any("rag" in path.lower() for path in paths):
        stack.add("RAG")

    return sorted(stack)

# 从目录结构里找模块边界 把顶层目录、Maven 子模块抽出来
# 输出：模块列表，如 ["src", "tests", "docs", "api"]
def analyze_modules(scan: dict[str, Any]) -> list[str]:
    directories = scan["directories"]
    modules: list[str] = []

    # 取顶层目录作为模块
    top_level = sorted({directory.split("/")[0] for directory in directories if "/" not in directory})
    for name in top_level[:20]:
        modules.append(name)

    # 对 Maven 项目，额外识别有 pom.xml 的子目录作为子模块
    maven_modules = [
        directory
        for directory in directories
        if directory.count("/") <= 1 and any(
            file["path"] == f"{directory}/pom.xml" for file in scan["files"]
        )
    ]
    for module in maven_modules:
        if module not in modules:
            modules.append(module)

    return modules[:30]

# 在所有文件中，找出路径里包含 controller 的文件，作为 API 入口线索。
# 这只是"线索"，不是"API 列表"。
# 真正的 API 提取需要解析 AST（抽象语法树）或注解，这个函数只是给后续分析提供起点。
# 命名用 hints 而非 apis，很准确。
def extract_api_hints(scan: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    controller_files = [file["path"] for file in scan["files"] if "controller" in file["path"].lower()]
    for path in controller_files[:20]:
        hints.append(path)
    return hints

# 风险和建议生成
# 核心逻辑：一组基于规则的条件判断：
# 没有 README：	上手成本高，补充 README
# 没有 Docker：补充容器化
# 文件数 ≥ 500：增加架构图
# Java + Maven 但无清晰模块：模块边界不明显，梳理分层
# 有 SQL：建立表结构映射
# 有 MCP：增加权限和日志
# 最后兜底：如果没有风险，提示"未发现明显结构性风险"；没有建议，提示"进入下一阶段"。
# 学习要点：这种"根据信号生成发现"的模式，本质上是把架构师的经验变成了规则。每个 if 都是一条经验知识。
def generate_findings(scan: dict[str, Any], tech_stack: list[str], modules: list[str]) -> tuple[list[str], list[str]]:
    risks: list[str] = []
    suggestions: list[str] = []
    key_files = set(scan["key_files"])
    file_count = len(scan["files"])

    if not any(path.lower().startswith("readme") or path.lower().endswith("/readme.md") for path in key_files):
        risks.append("未发现 README 文档，项目上手成本可能较高。")
        suggestions.append("补充 README，说明项目定位、启动方式、核心模块和常用命令。")

    if "Docker" not in tech_stack:
        suggestions.append("可以补充 Dockerfile 或 docker-compose，降低环境搭建成本。")

    if file_count >= 500:
        suggestions.append("项目文件较多，建议增加模块说明和架构图，方便新人理解。")

    if "Java" in tech_stack and "Maven" in tech_stack and not modules:
        risks.append("检测到 Maven/Java，但模块边界不明显，可能需要进一步梳理分层。")

    if "SQL" in tech_stack:
        suggestions.append("建议把数据库表结构和核心业务实体建立映射说明。")

    if "MCP" in tech_stack:
        suggestions.append("建议为 MCP 工具增加权限边界、调用日志和失败重试策略。")

    if not risks:
        risks.append("未发现明显结构性风险，后续可接入更深入的代码质量分析。")
    if not suggestions:
        suggestions.append("建议进入第二阶段：加入代码审查 Agent 和 LLM 语义分析。")

    return risks, suggestions

# 质量评分
def quality_score(scan: dict[str, Any], tech_stack: list[str], risks: list[str]) -> int:
    score = 70
    if scan["key_files"]:
        score += 10
    if tech_stack:
        score += 10
    if len(scan["directories"]) > 3:
        score += 5
    score -= max(0, len(risks) - 1) * 5
    return max(0, min(100, score))

# 报告生成
def generate_report(
    scan: dict[str, Any],
    tech_stack: list[str],
    modules: list[str],
    api_hints: list[str],
    risks: list[str],
    suggestions: list[str],
    score: int,
) -> str:
    # 规则生成的 Markdown（fallback）
    stack_text = ", ".join(tech_stack) if tech_stack else "暂未识别"
    key_files = "\n".join(f"- `{item}`" for item in scan["key_files"][:30]) or "- 暂未发现"
    module_text = "\n".join(f"- `{item}`" for item in modules) or "- 暂未识别明显模块"
    api_text = "\n".join(f"- `{item}`" for item in api_hints) or "- 暂未发现 Controller/API 线索"
    risk_text = "\n".join(f"- {item}" for item in risks)
    suggestion_text = "\n".join(f"- {item}" for item in suggestions)
    mermaid_nodes = "\n".join(
        f"    A --> M{index}[{_safe_mermaid_label(module)}]" for index, module in enumerate(modules[:8], 1)
    ) or "    A --> B[待进一步分析]"

    fallback = f"""# {scan['project_name']} 项目分析报告

## 项目概览

- 项目路径：`{scan['root']}`
- 文件数量：{len(scan['files'])}
- 目录数量：{len(scan['directories'])}
- 识别技术栈：{stack_text}
- 初步质量评分：{score}/100

## 关键文件

{key_files}

## 模块结构

{module_text}

## API / 入口线索

{api_text}

## 架构草图

```mermaid
graph TD
    A[{_safe_mermaid_label(scan['project_name'])}]
{mermaid_nodes}
```

## 风险提示

{risk_text}

## 优化建议

{suggestion_text}

## 下一步建议

- 接入代码审查 Agent，分析异常处理、重复代码、安全风险和 SQL 风险。
- 接入 RAG 知识加工 Agent，把 README、接口文档、SQL 和部署文档沉淀为可检索知识库。
- 接入 LangGraph Checkpoint，把任务执行过程保存为可回放的时间线。
"""
    # LLM 增强的架构理解
    architecture = llm_provider.generate(
        "你是 Jaycode 的项目架构讲解 Agent。请基于扫描事实解释项目结构、阅读路径和治理建议，不要编造不存在的文件。",
        (
            "请输出中文 Markdown，包含：项目定位、架构理解、关键模块阅读顺序、风险理解、学习路径。"
            "只基于给定事实。\n"
            f"项目：{scan['project_name']}\n"
            f"技术栈：{tech_stack}\n"
            f"模块：{modules}\n"
            f"关键文件：{scan.get('key_files', [])[:30]}\n"
            f"API 线索：{api_hints}\n"
            f"风险：{risks}\n"
            f"建议：{suggestions}"
        ),
        "",
        agent="project_analyzer",
        prompt_version="project_analyzer.architecture.v1",
    )
    if architecture:
        return f"{fallback}\n\n## LLM 架构理解\n\n{architecture}\n"
    return fallback

# 辅助函数
# Mermaid 语法中，[]{}() 等字符有特殊含义。这个函数把它们替换成空格，防止图表渲染崩溃
def _safe_mermaid_label(value: str) -> str:
    return re.sub(r"[\[\]{}()<>|]", " ", value).strip() or "Project"
