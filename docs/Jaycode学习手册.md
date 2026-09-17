# Jaycode 代码结构与内容学习手册

> 面向想从 `five_weeks_gap_analysis` 延伸学习多 Agent 工程化项目的读者。
> 这份手册只保留一条主线：先看架构，再按优先级学习核心文件。
>
> 运行状态更新（2026-09-17）：本文出现的 SQLite Store 是用于讲解兼容实现与演进过程；正式 Jaycode 已使用统一 `PersistenceStores` 连接 PostgreSQL `jayagent_studio`，RAG 使用同库 pgvector。日常启动请以 [Jaycode 启动方式](Jaycode%20启动方式.md) 为准。

## 1. 项目定位

Jaycode 是一个面向 **软件项目理解与工程治理** 的多 Agent 工作台。

它不是传统 IDE，也不是单纯聊天壳子，而是把下面这些能力组合到一起：

- 项目扫描与结构分析
- 代码审查与风险识别
- RAG 知识库治理
- 长期记忆管理
- 可视化工作流编排
- Agent 协作编排
- MCP 工具治理
- Skill 插件体系
- LLM 可观测与评测
- 人工审核与任务恢复

### 标准任务执行流程

1. 用户发起任务 → FastAPI 创建任务 [[FastAPI]]
2. Harness Runtime 初始化任务上下文，持续记录事件轨迹
3. Harness 调度 LangGraph 执行多 Agent 协作，按需调用 Skill、LLM、RAG、MCP 工具
4. **策略拦截：敏感操作强制人工审核、权限校验**
5. 全链路 Trace、产物、日志持久化存储
6. Reporter 汇总输出标准化治理报告

### 最核心创新亮点（区分普通 LangGraph 项目，重点学习）[[Jaycode/docs/亮点补充/Harness Runtime|Harness Runtime]]

#### 1. Harness Runtime：自研治理运行时（核心骨架）

绝大多数 LangGraph 项目只使用框架原生`checkpoint`做状态保存；

本项目**在 LangGraph 外层封装一层统一运行时**，解决生产落地痛点：

- 统一管理全任务上下文、事件时间线；
- 内置策略引擎，支持人工介入审核（Human-in-the-loop）；
- 统一持久化所有产物、日志、Trace；
- 支持任务中断、断点恢复、重试、失败可视化排查。

> 通俗理解：LangGraph 负责「流程怎么走」；Harness 负责「流程运行过程如何管控、审计、持久化」。

#### 2. 可视化可执行 Workflow（不是静态流程图）

前端拖拽画布定义节点与连线，最终**编译为可运行的 LangGraph Graph 实例**。

市面上很多低代码 Agent 平台只是画图展示；这个画布配置直接驱动执行。

#### 3. 全套 LLM 可观测治理体系

- 保存 Prompt 版本、模型配置；
- 完整调用 Trace、Token 消耗、费用统计；
- 支持失败降级（Fallback）、A/B 对比测试；
- 可以按不同 Agent 独立配置大模型。

#### 4. 高度完善、带安全管控的 Skill 插件体系（重中之重）[[Jaycode/docs/亮点补充/Skill 插件体系：企业级 Agent 的“应用商店”|Skill 插件体系：企业级 Agent 的“应用商店”]]

Skill = 可复用能力单元（代码审查、安全扫描、RAG 加工等）

分为两类，做安全隔离：

1. **Prompt Skill**
    
    仅加载`SKILL.md`提示词，**不会执行任何外部代码**，风险极低。
2. **Code Skill（代码插件）**
    
    可执行 Python 脚本，提供两层安全控制：
    
    - **权限分级**：safe、项目读、网络访问、文件系统等；
    - **Docker 沙箱隔离执行**：
        
        ✅ 禁用外网 `--network none`
        
        ✅ 文件系统只读
        
        ✅ 限制 CPU、内存、进程数量
        
        ✅ 执行完毕自动销毁临时容器
    

**审批模型（工业级安全设计）**

```
审批唯一键 = skill_code + agent_code
```

`skill_console`（页面手动测试）、`workflow_runner`（工作流自动执行）是两套独立身份；

**手动测试审批 ≠ 自动工作流审批**，防止插件在自动化流程中被意外调用。

配套能力：版本快照、升级对比、回滚、依赖校验、内置测试用例。

#### 5. 治理化 RAG（区别于 Demo 级简易检索）[[Jaycode/docs/亮点补充/治理化 RAG（区别于 Demo 级简易检索）|治理化 RAG（区别于 Demo 级简易检索）]]

不再只是文档切片 + 向量查询，面向**项目知识库生产化治理**：

- 增量索引：文件内容 Hash 比对，无变更跳过；变更文件生成新版本；
- 文档版本管理，历史版本保留用于审计；
- 混合检索：BM25 关键词 + 向量检索 + RRF 融合；可选 LLM Rerank 重排；
- 文档 ACL 权限控制，不同用户可见文档隔离；
- **Benchmark 评测体系**：内置 Chunk 黄金数据集（Gold Set），自动计算 Recall@K、Precision@K、MRR，可量化评估 RAG 效果。

#### 6. 受控长期记忆（防止记忆无限膨胀、过时干扰）

通用方案：直接把对话片段丢进向量库；

本项目设计完整记忆治理流水线：

```
用户消息 → 记忆提取器(LLM/规则双模式) → 候选记忆
→ 敏感过滤 → 质量打分 + 冲突检测 → 需要用户确认才能入库
→ 设置生命周期（90天复核）
```

核心特点：

- 记忆不会自动写入知识库，**必须人工确认**；
- 过期记忆不会直接删除，标记`expired`退出检索，但保留审计记录；
- 用户 / 项目 / 团队三层隔离，细粒度访问权限；
    
    避免陈旧信息持续干扰 Agent 推理。

#### 7. Benchmark 标准化评测平台

支持对 LLM、RAG、Workflow、MCP 工具、多 Agent 协作流程自动化评测，输出完整指标。

解决一个痛点：很多 Agent 项目只能人工肉眼判断效果，无法量化迭代优化。


可以把它理解为：

> 一个“能看项目、能审代码、能沉淀知识、能编排流程、能做治理”的多 Agent 工程化中台。

---

## 2. 目录总览

仓库核心目录如下：

```text
Jaycode/
├── app/                  # 后端主代码
├── web/                  # 前端工作台
├── docs/                 # 分阶段设计文档
├── examples/             # API / 工作流示例
├── tests/                # 测试
├── pyproject.toml        # Python 项目配置
├── README.md             # 项目总说明
└── docker-compose.pgvector.yml
```

重点目录：

- `app/graphs/`：LangGraph 编排逻辑
- `app/harness/`：任务执行治理层
- `app/agents/`：面向业务的 Agent 能力实现
- `app/persistence/`：记忆、RAG、任务持久化
- `app/skills/`：可扩展技能系统
- `app/api/routes.py`：统一 API 出口
- `web/src/App.tsx`：前端交互入口

---

## 3. 整体架构

项目执行链路：

```text
用户
  -> React 前端
  -> FastAPI API
  -> Harness Runtime 任务治理
  -> LangGraph / Skill / MCP / RAG / LLM
  -> 持久化与审计
  -> 报告与前端展示
```

### 3.1 分层目的

这个项目刻意拆成几层：

- **API 层**：接收请求、返回响应
- **Graph 层**：负责 Agent 流程编排
- **Harness 层**：负责任务上下文、事件、审计、恢复
- **Agent 层**：负责具体分析、审查、生成能力
- **Persistence 层**：负责保存数据
- **Skills 层**：负责插件化执行

这种拆法很适合学习企业级 Agent 项目。

---

## 4. 推荐学习路径 [[Jaycode/docs/亮点补充/路径补充|路径补充]]

为了避免来回跳转，这份手册只保留一条主线学习路径。按这个顺序来就够了。

### 4.1 第 1 层：先建立项目骨架

1. `README.md`
2. `app/agents/project_tools.py`
3. `app/agents/code_review_tools.py`
4. `app/graphs/studio_graphs.py`
5. `app/graphs/workflow_compiler.py`
6. `app/harness/runtime.py`

这一层是最重要的，因为它直接决定你怎么理解这个项目的 Agent 骨架。

#### 4.1.1 `README.md`

- 作用：项目总说明
- 结构：项目定位、架构图、能力列表、启动方式、产品预览
- 学习重点：先用它建立系统整体认知

#### 4.1.2 `app/agents/project_tools.py`

- 作用：项目理解 Agent 的核心工具集
- 结构：项目扫描、技术栈识别、模块分析、API 线索提取、风险与建议生成
- 学习重点：把文件系统扫描变成结构化的项目画像


#### 4.1.3 `app/agents/code_review_tools.py`

- 作用：代码审查 Agent 的核心工具集
- 结构：单文件审查、项目审查、规则扫描、安全模式识别、调用链分析、LLM 语义审查兜底
- 学习重点：理解“规则分析 + 结构分析 + LLM 语义分析”的组合审查方式

```
常量定义
├── SOURCE_SUFFIXES          # 需要审查的文件后缀白名单
└── SECRET_PATTERNS          # 硬编码密钥检测正则

═══════════════════════════════════════
公开入口（2个）
═══════════════════════════════════════
├── review_project()         # 审查整个项目
│   ├── scan_project()           → 复用 project_tools
│   ├── _safe_read()             → 读文件（300KB 上限）
│   ├── _review_file()           → 逐行规则扫描
│   ├── _build_risks()           → 项目级风险汇总
│   ├── _build_suggestions()     → 项目级建议（含 LLM）
│   ├── _build_suggestion_records() → 结构化操作建议
│   ├── _score()                 → 项目级评分
│   └── _report()                → 项目级报告
│
└── review_single_file()     # 审查单个文件
    ├── _safe_read_limited()     → 读文件（可设上限）
    ├── _review_file()           → 逐行规则扫描
    ├── _infer_responsibilities()→ 职责推断
    ├── _extract_dependencies()  → 依赖提取
    ├── _extract_api_surface()   → 公开接口提取
    ├── _build_call_chain_context()
    │   ├── _extract_local_symbols()    → 提取本地符号
    │   ├── _find_inbound_references()  → 找入站引用
    │   ├── _extract_outbound_calls()   → 找出站调用
    │   └── _call_chain_summary()       → 调用链摘要
    ├── _assess_testability()    → 可测试性评估
    ├── _build_file_risks()      → 文件级风险
    ├── _build_file_suggestions()→ 文件级建议
    ├── _semantic_file_review()  → LLM 语义审查
    │   └── _semantic_fallback()     → LLM 不可用时的兜底
    └── _file_report()           → 文件级报告

═══════════════════════════════════════
私有辅助函数
═══════════════════════════════════════
文件读取
├── _safe_read()              # 安全读文件（>300KB 跳过）
└── _safe_read_limited()      # 安全读文件（截断到 max_chars）

规则扫描
└── _review_file()            # 逐行正则匹配，返回 finding 列表

结构分析
├── _infer_responsibilities() # 路径关键词 + 代码特征 → 职责列表
├── _extract_dependencies()   # 按语言提取 import/dependency
└── _extract_api_surface()    # 提取公开函数/方法/HTTP 路由

调用链分析
├── _build_call_chain_context()
├── _extract_local_symbols()  # 提取类/函数/变量名
├── _find_inbound_references()# 遍历项目找谁引用了这些符号
├── _extract_outbound_calls() # 提取本文件调用的外部函数
└── _call_chain_summary()     # 生成调用链文字摘要

可测试性
└── _assess_testability()     # 评分 + 扣分原因列表

LLM 审查
├── _semantic_file_review()   # 调用 LLM 做语义审查
└── _semantic_fallback()      # LLM 失败时的确定性总结

报告生成
├── _file_report()            # 单文件审查报告
└── _report()                 # 项目级审查报告

风险与建议
├── _build_risks()            # 项目级风险（从 findings 汇总）
├── _build_file_risks()       # 文件级风险
├── _build_suggestions()      # 项目级建议（含 LLM 生成）
├── _build_file_suggestions() # 文件级建议
└── _build_suggestion_records() # 结构化可操作建议

评分
└── _score()                  # 基础分 90，按 severity 扣分

工具函数
├── _unique()                 # 列表去重（保持顺序）
├── _finding()                # 构造一条 finding 字典
├── _risk_from_severity()     # severity → risk_level 映射
├── _action_for_finding()     # 根据 category 给出修复动作
└── _test_case_for_finding()  # 根据 category 生成测试用例描述
```
#### 4.1.4 `app/graphs/studio_graphs.py`

- 作用：固定协作图定义
- 结构：`code_review_graph`、`rag_process_graph`、`learning_coach_graph`、`workflow_runner_graph`、`collaboration_graph`
- 学习重点：理解 Planner、Analyzer、Reviewer、RAG、Supervisor、Reporter 如何被串成协作流程

```
1. StudioState           → 共享状态定义（所有节点共用的"工作台"）
2. 4 个单节点子图         → 把 Skill 包装成 LangGraph 图
3. _build_collaboration_graph() → 多 Agent 协作主图
   ├── planner           → 理解目标，制定计划
   ├── project_analyzer  → 执行项目分析子图
   ├── code_reviewer     → 执行代码审查子图
   ├── rag_processor     → 执行 RAG 知识加工子图
   ├── supervisor        → 质量监督，汇总意见
   ├── human_review      → 人工审核卡点
   └── reporter          → 生成最终报告
```

#### 4.1.5 `app/graphs/workflow_compiler.py`

- 作用：动态工作流编译器
- 结构：`WorkflowState`、节点标准化、边标准化、验证、编译、恢复执行、人工审核
- 学习重点：理解动态工作流怎么从 JSON 变成 LangGraph 可执行图

```
一、编译工作流

compile_workflow_graph(workflow_name, nodes, edges, entry_node_id)

接收前端传来的节点列表和连线，动态构建 LangGraph 图。

### 二、运行工作流

run_compiled_workflow(...)  # 完整运行
run_task_workflow(...)      # 从任务状态运行
resume_task_workflow(...)   # 从断点恢复

### 三、验证工作流

validate_workflow_definition(nodes, edges)

运行前检查：节点类型是否合法、边是否连通、有没有死循环。
```
 
`studio_graphs.py` 的 `collaboration_graph` 是**一个固定的 7 节点流水线**。`workflow_compiler.py` 让用户**自己选节点、自己连线**。

##### 关键设计

**断点恢复**：工作流卡在 `human_review` 时，`_build_resume_checkpoint()` 保存完整状态。人工审批后，`resume_task_workflow()` 从断点继续执行，不需要重新跑。

**错误重试**：每个节点支持 `retry_count`，执行失败自动重试，超过次数才标记失败。

**条件路由**：边可以设置条件（`always`、`on_status`、`contains`），根据上一个节点的执行结果决定走哪条分支。

**输入映射**：节点可以设置 `input_from`，指定从哪个节点的输出取数据作为输入。


#### 4.1.6 `app/harness/runtime.py`

- 作用：任务治理层
- 结构：上下文创建、事件记录、图运行、结果提取、治理产物落盘、任务状态判断
- 学习重点：理解为什么 Agent 系统需要治理层，而不只是一个“调用模型”的入口

**在所有图（协作图/动态工作流）的外面包了一层，统一管理任务的创建、执行、状态、事件、持久化。**

 **它和之前学的图的关系**

之前学的：
  collaboration_graph.invoke()    → 跑协作流程
  workflow_compiler.run_task_workflow() → 跑动态工作流
  
现在学的：
  HarnessRuntime.run_graph() → 包在它们外面
    ├── 创建任务上下文
    ├── 记录开始事件
    ├── 跑图
    ├── 保存结果
    ├── 记录结束事件
    └── 异常处理

 **两个核心方法**:
 
 **create_context() — 创建任务**
```
def create_context(self, goal, project_path, variables):
    context = AgentExecutionContext(...)           # 创建上下文
    task_store.create_task(...)                    # 任务信息落库
    context.events.emit("task", "任务已创建")       # 记录事件
    task_store.append_event(...)                   # 事件落库
    return context
```

**做了什么**：每次用户发起任务，先创建一个上下文对象，把任务信息和初始事件存到数据库。

**run_graph() — 运行并治理**

```
def run_graph(self, context, graph_runner, input_state):
    # 1. 更新任务状态为 running
    context.status = "running"
    task_store.update_task(...)
    
    # 2. 记录开始事件
    context.events.emit("task", "任务开始执行")
    
    try:
        # 3. 真正跑图
        result = graph_runner({**input_state, "task_id": context.task_id, "events": context.events.to_list()})
        
        # 4. 提取结果
        final_report = _extract_final_report(result)
        public_result = _public_result(result)
        
        # 5. 持久化
        task_store.save_artifact(...)     # 保存图执行结果
        task_store.save_artifact(...)     # 保存断点（如果有）
        task_store.save_artifact(...)     # 保存治理信息
        task_store.update_task(...)       # 更新任务状态
        
        # 6. 合并事件
        graph_events = result.get("events", [])
        combined_events = context.events + graph_events
        
        # 7. 判断最终状态
        context.status = "waiting_review" 还是 "completed"
        
        return {
            "task_id": context.task_id,
            "status": context.status,
            "events": combined_events,
            "result": public_result,
        }
    
    except Exception:
        # 8. 异常处理
        context.status = "failed"
        task_store.update_task(...)
        context.events.emit("error", str(exc))
        raise
```

**它解决了什么问题**

之前学图的时候，图只管"怎么跑"，不管：

- 任务谁创建的、什么时候创建的
    
- 跑完之后结果存哪
    
- 失败了怎么记录
    
- 事件时间线谁维护
    

##### 对应之前学的概念

| 之前学的概念         | 代码体现                                                           |
| -------------- | -------------------------------------------------------------- |
| **统一管理全任务上下文** | `AgentExecutionContext` 包含 task_id、goal、project_path、variables |
| **事件时间线**      | `context.events.emit()` 记录每个关键节点                               |
| **统一持久化所有产物**  | `task_store.save_artifact()` 保存图结果、断点、治理信息                     |
| **任务中断、断点恢复**  | `resume_checkpoint` 保存到 `task_store`                           |
| **失败可视化排查**    | 异常时记录 error 事件，状态标记为 failed                                    |


### 4.2 第 2 层：再补系统能力

7. `app/api/routes.py`
8. `app/persistence/rag_store.py`
9. `app/persistence/memory_store.py`
10. `app/skills/registry.py`
11. `app/skills/executor.py`
12. `app/providers/llm_provider.py`

#### 4.2.1 `app/api/routes.py`

- 作用：后端统一 API 总入口
- 结构：项目分析、代码审查、RAG、学习计划、任务、工作流、Skill、MCP、Benchmark 等接口
- 学习重点：理解系统能力如何被统一暴露给前端和外部调用方

##### 接口分类速览

|分类|核心接口|调什么|
|---|---|---|
|**项目分析**|`POST /projects/analyze`|`project_analyzer_graph.invoke()`|
|**代码审查**|`POST /code/review`|`code_review_graph.invoke()`|
|**知识库**|`POST /rag/process` `POST /rag/query`|`rag_process_graph` / `rag_store`|
|**学习教练**|`POST /learning/coach/plan`|`learning_coach_graph.invoke()`|
|**工作流**|`POST /workflows/run`|`run_compiled_workflow()`|
|**任务**|`POST /tasks/run` `POST /tasks/collaborate`|`harness_runtime.run_graph()`|
|**人工审批**|`POST /tasks/{id}/approve`|`resume_task_workflow()`|
|**Skill**|`POST /skills/{code}/execute`|`execute_skill()`|
|**MCP 工具**|`POST /mcp/tools/call`|`mcp_provider.call_tool()`|
|**Benchmark**|`POST /benchmarks/rag/run` 等|各评测函数|
|**长期记忆**|`POST /memories/extract` `POST /memories/{id}/confirm`|`memory_store`|
|**LLM 管理**|`GET /llm/status` `POST /llm/prompts`|`llm_provider`|

#### 4.2.2 `app/persistence/rag_store.py`

- 作用：RAG 知识库存储与检索层
- 结构：文档入库、查询、版本、Gold Case 评测、ACL 控制
- 学习重点：理解“可治理的知识库”而不是简单向量检索

第一部分：SQLiteRagStore     — SQLite 实现
第二部分：EmbeddingProvider  — 向量化服务
第三部分：PgVectorRagStore   — PostgreSQL + pgvector 实现
第四部分：工厂函数 + 工具函数 — 创建实例、检索算法、格式化
第五部分：rag_store 全局实例

```
# 建表

    def _init_schema(self) -> None:
        with self._connection() as conn:
            # 建基础表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_document (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 查已有字段
            document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rag_document)").fetchall()}
            
            # 缺什么加什么
            # 逐个检查 5 个新字段，如果表里没有就加。
            # 从旧版本升级：旧数据保留，新字段用 DEFAULT 值填充
            for name, definition in {
                "content_hash": "TEXT",
                "version": "INTEGER NOT NULL DEFAULT 1",
                "is_current": "INTEGER NOT NULL DEFAULT 1",
                "valid_to": "TEXT",
                "acl_json": "TEXT NOT NULL DEFAULT '[\"*\"]'",
            }.items():
                if name not in document_columns:
                    conn.execute(f"ALTER TABLE rag_document ADD COLUMN {name} {definition}")
            chunk_columns = {row["name"] for row in conn.execute("PRAGMA table_info(rag_chunk)").fetchall()}
            if "document_version" not in chunk_columns:
                conn.execute("ALTER TABLE rag_chunk ADD COLUMN document_version INTEGER NOT NULL DEFAULT 1")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_document_current ON rag_document(collection, path, is_current)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_gold_case (
                    case_id TEXT PRIMARY KEY,
                    collection TEXT NOT NULL,
                    question TEXT NOT NULL,
                    expected_chunk_ids_json TEXT NOT NULL,
                    expected_paths_json TEXT NOT NULL,
                    expected_keywords_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
```

经过建表 + 迁移后，`rag_document` 的完整字段：

|字段|来源|作用|
|---|---|---|
|`id`|建表|主键|
|`collection`|建表|集合名|
|`path`|建表|文档路径|
|`size`|建表|文件大小|
|`created_at`|建表|创建时间|
|`content_hash`|ALTER 加的|内容哈希，用于增量索引|
|`version`|ALTER 加的|版本号|
|`is_current`|ALTER 加的|是否当前版本|
|`valid_to`|ALTER 加的|旧版本失效时间|
|`acl_json`|ALTER 加的|权限列表|

`PgVectorRagStore`功能上和 `SQLiteRagStore` 一样，但多了**真正的向量检索能力**。
##### 和 SQLiteRagStore 的核心区别

|          | SQLiteRagStore | PgVectorRagStore         |
| -------- | -------------- | ------------------------ |
| **向量存储** | 无              | `embedding vector(1536)` |
| **向量化**  | 不需要            | `EmbeddingProvider`      |
| **语义检索** | token 重叠率      | 余弦相似度 `<=>`              |
| **向量索引** | 无              | IVF flat 索引（加速检索）        |
##### 治理特性一：增量索引 — "别重复干已经干过的活"

**问题**：1000 个文档，改了 2 个。Demo 级做法是全量重建索引，浪费时间。

**实现**：

content_hash = _content_hash(chunks)       # 计算新内容 SHA256
existing = 查当前版本
if existing and existing["content_hash"] == content_hash:
    continue                               # 没变 → 跳过

每次入库前先比对 Hash，只有内容变了的文档才重新切片入库。

---
##### 治理特性二：版本管理 — "上次的回答基于什么？"

**问题**：用户投诉"上个月 AI 回答和现在不一样"。没有版本管理，旧数据已被覆盖，死无对证。

**实现**：

 旧版本标记失效
UPDATE rag_document SET is_current = FALSE, valid_to = now

 新版本入库
INSERT INTO rag_document (version = 旧版本号 + 1, is_current = TRUE)

 切片也带版本号
INSERT INTO rag_chunk (document_version = 新版本号)

每个文档保留完整版本历史。审计时可以回溯"当时 AI 用的是 V3 版本的知识库"。

---

##### 治理特性三：ACL 权限控制 — "财务数据研发部不该搜到"

**问题**：企业内部文档有权限隔离。Demo 级做法是所有文档公有。

**实现**：

 入库时存权限
acl_json = '["*"]'          # 所有人可见
acl_json = '["alice","bob"]'  # 只有 alice 和 bob 可见

 查询时过滤
visible = [row for row in rows if _acl_allows(row["acl_json"], actor_id)]

在数据库查询后就做拦截，不是返回结果后再过滤。

---

##### 治理特性四：混合检索 — "向量查不到的关键词能兜底"

**问题**：纯向量检索对精确术语（如 "AK-47"、"ERROR_CODE_5001"）效果差。

**实现**：

```

bm25_scores = _bm25_scores(query_terms, documents)         # 关键词分数
semantic_scores = 向量余弦相似度                            # 语义分数


 RRF 融合两个排名
score = 1/(60 + bm25_rank) + 1/(60 + semantic_rank)

BM25 管精确命中，向量管语义理解，RRF 把两种排名加权合并。

```

---

##### 治理特性五：Gold Set 评测 — "改了切片策略，效果变好还是变差？"

**问题**：Demo 级靠人工看几条结果判断"应该还行"。无法量化，无法对比。

**实现**：
```
 存标准问答对
INSERT INTO rag_gold_case (
    question = "怎么取消订单？",
    expected_chunk_ids = ["order.md#chunk-3", "faq.md#chunk-7"],
    expected_keywords = ["取消", "退款", "订单"]
)
```

 评测时：用这些问题去搜，对比期望结果，算 Recall@K、Precision@K

---

##### 治理特性六：存储可替换 — "开发用 SQLite，生产切 pgvector"

**问题**：开发时不想装 PostgreSQL，生产时需要向量检索。

**实现**：

```
def create_rag_store():
    if 配置 == "pgvector":
        return PgVectorRagStore()    # 带向量检索
    return SQLiteRagStore()          # 零配置，关键词检索
rag_store = create_rag_store()
```

两个类实现完全相同的接口，上层调用方无感知。

##### Demo 级 vs 治理级 对比

|场景|Demo 级 RAG|rag_store.py|
|---|---|---|
|文档更新|全量重建|Hash 比对，只更新变化的|
|有人投诉回答变了|无法追溯|查历史版本，看当时用的是 V3|
|财务文档|所有人都能搜到|ACL 控制，只允许财务团队|
|搜"AK-47"|返回一堆"步枪"|BM25 精确命中 "AK-47"|
|换了切片大小|"感觉变好了"|Gold Set 跑一遍，Recall 从 0.82 → 0.91|
|部署|必须装向量数据库|开发用 SQLite，生产切 pgvector|


#### 4.2.3 `app/persistence/memory_store.py`

- 作用：长期记忆存储层
- 结构：记忆候选、确认、冲突替换、过期、删除
- 学习重点：理解记忆和知识库的区别，以及记忆如何被治理

##### 1. `SQLiteMemoryStore.__init__`

作用：

- 初始化记忆库
- 设定 SQLite 数据库路径
- 自动创建父目录
- 立刻初始化表结构

你可以理解成：

> 创建记忆系统实例时，先把数据库和表准备好。

参考：

- [app/persistence/memory_store.py](../app/persistence/memory_store.py)

---

##### 2. `_connect()`

作用：

- 打开 SQLite 连接
- 设置 `row_factory = sqlite3.Row`

这样查询结果就能像字典一样访问字段。

你可以理解成：

> 每次操作数据库前，先开一个标准连接。

---

##### 3. `_connection()`

作用：

- 这是一个上下文管理器
- 自动处理：
    - 打开连接
    - `yield` 给调用方使用
    - 结束后自动 `commit`
    - 最后关闭连接

你可以理解成：

> 数据库操作的安全包装器，避免你手动 commit/close。

---

##### 4. `_init_schema()`

作用：

- 创建 `memory_record` 表
- 创建索引
- 检查旧字段是否存在
- 对旧数据做治理字段补齐
- 对旧记录做质量与保留策略回填

它做的不是单纯建表，而是完整定义了记忆的治理模型。

`memory_record` 里核心字段包括：

- `scope`
- `scope_id`
- `memory_type`
- `memory_key`
- `content`
- `confidence`
- `status`
- `extraction_source`
- `quality_score`
- `retention_policy`
- `expires_at`
- `conflict_with`
- `rag_path`

你可以理解成：

> 这一步是在定义“记忆应该怎么被管理”，而不是只定义存储格式。

---

##### 5. `extract_candidates()`

作用：

- 从一段文本里抽取候选记忆
- 支持指定作用域：
    - `user`
    - `project`
    - `team`
- 自动去重
- 自动检测是否和已有记忆冲突
- 给候选记忆补上治理字段
- 写入 `memory_record`

这是这个文件最核心的方法之一。

###### 它的流程是：

1. 调 `_extract_memory_candidates(text)`
2. 生成候选记忆
3. 算 `content_hash`
4. 检查是否重复
5. 检查是否存在冲突记忆
6. 调 `_memory_governance()`
7. 写入数据库
8. 返回候选列表

你可以理解成：

> 把自然语言转成“可审核的记忆候选”。

---

##### 6. `list_memories()`

作用：

- 列出记忆记录
- 支持按 `scope`、`scope_id`、`status` 过滤
- 调用前会先执行 `expire_due_memories()`

也就是说它不是直接查表，而是会先清理该过期的记忆。

你可以理解成：

> 查记忆列表之前，先把该过期的记忆状态更新掉。

---

##### 7. `get_memory()`

作用：

- 根据 `memory_id` 查询单条记忆
- 查询前先执行过期检查

它和 `list_memories()` 类似，只是查单条。

你可以理解成：

> 获取一条记忆详情，并保证状态是最新的。

---

##### 8. `confirm()`

作用：

- 把候选记忆确认成正式记忆
- 如果有冲突记忆，会把旧记忆标记成 `superseded`
- 把当前记忆标记成 `confirmed`
- 记录 `rag_path`
- 记录 `confirmed_at`

这是“记忆入库生效”的关键动作。

你可以理解成：

> 用户确认后，这条记忆才真正变成长期记忆。

---

##### 9. `expire_due_memories()`

作用：

- 检查哪些记忆到期了
- 如果 `expires_at` 已过期，就把状态改成 `expired`

这个方法会把候选记忆和已确认记忆里该过期的都处理掉。

你可以理解成：

> 定期把不该继续生效的记忆自动降级为过期。

---

##### 10. `reject()`

作用：

- 把某条记忆标记成 `rejected`

这是用户明确不想保留这条记忆时使用的。

你可以理解成：

> 这条候选记忆不采纳。

---

##### 11. `delete()`

作用：

- 直接删除某条记忆记录

这比 `reject()` 更彻底。

你可以理解成：

> 从数据库里真正移除这条记忆。

---

##### 12. `_extract_memory_candidates(text)`

作用：

- 这是“抽取策略入口”
- 先做文本清洗
- 如果文本太短或太长，直接不抽
- 先尝试 LLM 抽取
- LLM 不可用或没抽到时，回退到规则抽取

它返回两个东西：

- 候选列表
- 抽取来源：`llm` 或 `rule_fallback`

你可以理解成：

> 记忆抽取的总调度器。

---

##### 13. `_extract_with_llm(text)`

作用：

- 用 LLM 从文本里抽取长期记忆候选
- 只在 `DEV_AGENT_MEMORY_EXTRACTOR=llm` 且 LLM 可用时运行
- 输出必须是 JSON

它会调用：

- `llm_provider.generate_with_status(...)`

如果模型没有返回正确内容，就会回退。

你可以理解成：

> 更智能的记忆抽取方式，但依赖模型。

---

##### 14. `_extract_with_rules(clean)`

作用：

- 规则抽取的回退方案
- 通过关键词判断用户是否表达了稳定偏好
- 比如“我喜欢”“我希望”“请用”“优先关注”等

它适合非常显式的偏好提取。

你可以理解成：

> 不靠大模型，靠固定规则抓记忆。

---

##### 15. `_normalize_llm_candidate(candidate)`

作用：

- 规范化 LLM 抽取结果
- 校验 `memory_type`
- 清洗 `memory_key`
- 清洗 `content`
- 限制长度
- 过滤敏感信息
- 处理 `confidence`

你可以理解成：

> 把模型输出变成可安全入库的标准结构。

---

##### 16. `_contains_sensitive_text(text)`

作用：

- 检测内容里有没有敏感信息
- 比如：
    - `api_key`
    - `password`
    - `secret`
    - `token`

你可以理解成：

> 防止把敏感内容误存成长期记忆。

---

##### 17. `_json_object(text)`

作用：

- 从一段 LLM 输出里截取 JSON 对象
- 处理 ```json 代码块
- 处理前后多余文本

你可以理解成：

> 从模型文本里尽量抠出有效 JSON。

---

##### 18. `_memory_extractor_mode()`

作用：

- 决定当前记忆抽取模式
- 优先读环境变量 `DEV_AGENT_MEMORY_EXTRACTOR`
- 如果没有，再读 `.env`
- 默认返回 `llm`

你可以理解成：

> 控制记忆抽取到底走 LLM 还是规则的配置入口。

---

##### 19. `_memory_governance(candidate, extraction_source)`

作用：

- 给记忆候选计算治理字段
- 生成：
    - `quality_score`
    - `quality_reasons`
    - `retention_policy`
    - `expires_at`

它会考虑：

- 记忆类型是否稳定
- 是否来自 LLM
- 置信度如何

你可以理解成：

> 决定这条记忆值不值得长期保留。

---

##### 20. `_is_due(value, now)`

作用：

- 判断某个 `expires_at` 是否已到期

这是 `expire_due_memories()` 的辅助函数。

你可以理解成：

> 只负责判断“现在是不是过期了”。

---

##### 21. `memory_store = SQLiteMemoryStore()`

作用：

- 创建全局单例
- 整个项目里可以直接导入使用

你可以理解成：

> 项目启动后直接可用的记忆仓库对象。

---

##### 这份文件的核心思路

这份文件不是简单“存记忆”，而是一个完整的记忆治理流程：

```
用户输入
  -> 候选抽取（LLM / rule）
  -> 去重
  -> 冲突检测
  -> 质量评分
  -> 候选记录入库
  -> 用户确认 / 拒绝
  -> 过期 / 替换 / 删除
```

#### 4.2.4 `app/skills/registry.py`

- 作用：Skill 注册中心
- 结构：技能登记、查找、启用状态、元数据管理
- 学习重点：理解插件化能力如何先注册再执行

#### 4.2.5 `app/skills/executor.py`

- 作用：Skill 执行器
- 结构：依赖检查、权限检查、上下文传递、结果回传
- 学习重点：理解“能注册”不等于“能安全执行”

#### 4.2.6 `app/providers/llm_provider.py`

- 作用：模型接入层
- 结构：统一调用 LLM、fallback、trace、提示词和模型配置
- 学习重点：理解为什么项目不直接散落地调用 LLM API

### 4.3 第 3 层：最后看产品层

13. `web/src/App.tsx`
14. `web/src/api.ts`
15. `web/src/types.ts`
16. `app/marketplace/*`
17. `app/providers/mcp_provider.py`

#### 4.3.1 `web/src/App.tsx`

- 作用：前端工作台主入口
- 结构：运行、工作流、报告、追问、历史、LLM、MCP、Skills、Marketplace、Benchmark 等页面
- 学习重点：理解一个 Agent 平台前端应该有哪些控制台能力

#### 4.3.2 `web/src/api.ts`

- 作用：前端 API 封装
- 结构：统一请求方法、接口调用函数、数据转换
- 学习重点：理解前端如何和后端统一通信

#### 4.3.3 `web/src/types.ts`

- 作用：前端数据类型定义
- 结构：任务、事件、工作流、知识库、Skill 等类型
- 学习重点：理解前后端数据结构如何对齐

#### 4.3.4 `app/marketplace/*`

- 作用：插件市场
- 结构：安装、预览、卸载、目录管理
- 学习重点：理解可扩展平台如何管理资源包

#### 4.3.5 `app/providers/mcp_provider.py`

- 作用：MCP 工具接入层
- 结构：服务器注册、工具发现、调用、审批、日志
- 学习重点：理解外部工具如何被纳入统一治理

---

## 5. 按文件理解代码职责

这一部分只保留最关键的职责总结，避免和前面的路径重复。

### 5.1 `app/main.py`

- 职责：FastAPI 主入口
- 内容：创建应用、健康检查、挂载 API 和前端静态资源
- 架构位置：系统最外层入口

### 5.2 `app/api/routes.py`

- 职责：系统能力总入口
- 内容：把分析、审查、RAG、任务、工作流、Skill、MCP、评测统一暴露出去
- 架构位置：API 门户层

### 5.3 `app/graphs/studio_graphs.py`

- 职责：定义固定 Agent 协作图
- 内容：把多个 Agent 节点组合成可运行流程
- 架构位置：编排层

### 5.4 `app/graphs/workflow_compiler.py`

- 职责：把可视化工作流编译成 LangGraph
- 内容：节点/边标准化、校验、执行、恢复、人工审核
- 架构位置：动态编排层

### 5.5 `app/harness/runtime.py`

- 职责：任务治理
- 内容：上下文、事件、审计、结果、恢复点
- 架构位置：运行治理层

### 5.6 `app/agents/project_tools.py`

- 职责：项目理解
- 内容：扫描、识别、分析、评分、生成报告
- 架构位置：能力实现层

### 5.7 `app/agents/code_review_tools.py`

- 职责：代码审查
- 内容：规则扫描、上下文分析、LLM 语义审查
- 架构位置：能力实现层

### 5.8 `app/persistence/rag_store.py`

- 职责：知识库存储与检索
- 内容：入库、查询、版本、评测、ACL
- 架构位置：持久化层

### 5.9 `app/persistence/memory_store.py`

- 职责：长期记忆
- 内容：候选抽取、确认、冲突处理、过期
- 架构位置：持久化层

### 5.10 `app/skills/registry.py` 与 `app/skills/executor.py`

- 职责：技能管理与执行
- 内容：注册、权限、依赖、执行、回传
- 架构位置：插件能力层

### 5.11 `app/providers/llm_provider.py`

- 职责：统一模型接入
- 内容：模型调用、fallback、trace、提示词配置
- 架构位置：外部能力接入层

### 5.12 `web/src/App.tsx`

- 职责：前端工作台
- 内容：任务操作、工作流编排、结果展示、治理面板
- 架构位置：交互展示层

---

## 6. 你应该优先学到的能力

如果你的目标是尽快获得 Agent 开发能力，优先学这四类：

1. 项目扫描 + 技术栈识别
2. 规则审查 + LLM 语义审查
3. LangGraph 多 Agent 协作编排
4. 任务治理 + 事件 + 恢复点

这四类能力基本覆盖了一个 Agent 工程项目最核心的骨架。

---

## 7. 和五周学习路线的对应关系

| 学习阶段 | 对应内容 |
| --- | --- |
| 单 Agent 基础 | 项目扫描、代码审查、学习计划 |
| RAG 基础 | `rag_store`、`rag_tools`、`/rag/*` 接口 |
| 多 Agent 编排 | `studio_graphs.py` 的协作图 |
| 工程化治理 | `harness/runtime.py`、`persistence/*` |
| 可视化与产品化 | `web/src/App.tsx`、`routes.py` |
| 插件与扩展 | `skills/`、`marketplace/`、`providers/mcp_provider.py` |

---

## 8. 学习结论

Jaycode 的价值不在于某一个单点功能，而在于它把一个 Agent 项目该有的核心工程能力都串起来了：

- 有能力层
- 有编排层
- 有治理层
- 有持久化层
- 有前端工作台
- 有插件扩展
- 有评测与观测

对于想系统学习 Agent 开发的人来说，这个项目比“单纯的聊天机器人 demo”更值得研究。

它更接近你后续做工程化、多 Agent、RAG、工作流、评测、治理的真实落地方向。
