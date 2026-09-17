

> 这份手册是对《Jaycode学习手册.md》的补充，不重复讲已经掌握的主流程骨架，而是把“主流程之外还必须补的重点代码架构”系统梳理出来。  
> 目标是帮助你从“能看懂项目主线”进一步走到“能完整理解这个平台为什么这样设计、各层代码为什么这样分工、后续还该补哪些能力”。
>
> 运行状态更新（2026-09-17）：文中 SQLite 类名用于解释历史兼容层；正式运行时统一 Store 的权威后端为 PostgreSQL `jayagent_studio`。启动、停止与恢复流程见 [Jaycode 启动方式](Jaycode%20启动方式.md)。

## 1. 这份补充手册要解决什么

你现在已经掌握了项目主线：

- `README.md`
- `app/agents/project_tools.py`
- `app/agents/code_review_tools.py`
- `app/graphs/studio_graphs.py`
- `app/graphs/workflow_compiler.py`
- `app/harness/runtime.py`
- `app/api/routes.py`
- `app/persistence/rag_store.py`
- `app/persistence/memory_store.py`
- `app/skills/registry.py`
- `app/skills/executor.py`
- `app/providers/llm_provider.py`

但如果只学到这里，还是容易停留在“主流程知道了，细节和平台化能力不够清楚”的状态。  
这份手册要补的是：

1. 任务与工作流的持久化模型
2. 前端工作台的数据流和状态组织
3. RAG 与 Memory 的治理型设计
4. Skill / Marketplace / Sandbox 的完整插件链路
5. MCP 本地适配器与真协议客户端的区别
6. LLM 版本、Trace、Fallback、A/B 的治理机制
7. Benchmark 的闭环设计
8. 学习路线中容易被忽略但非常关键的辅助模块

---

## 2. 先把项目重新压成一张架构图

```text
User / Web Workbench
  -> FastAPI Routes
  -> Harness Runtime
  -> LangGraph / Workflow Compiler
  -> Agents / Skills / MCP / RAG / LLM
  -> Persistence / Benchmark / Audit
  -> Final Report / History / Review
```

如果再细一点：

```text
React Web
  -> API 门面层
  -> 任务治理层
  -> 编排层
  -> 能力实现层
  -> 持久化与治理层
  -> 外部模型/工具层
```

你可以把它记成：

- `web` 是操作台
- `api` 是统一入口
- `harness` 是任务治理
- `graphs` 是编排
- `agents` 是业务能力实现
- `skills` 是插件化能力
- `persistence` 是事实和知识保存
- `providers` 是外部模型和工具接入

---

## 3. 主流程之外，最值得补学的八个重点

### 3.1 SQLiteTaskStore：系统真正的事实中枢

关键文件：

- [app/persistence/sqlite_store.py](../app/persistence/sqlite_store.py)

这个文件不是简单的数据层，而是整个项目的“事实仓库”。  
它把任务、事件、产物、工作流、技能、MCP、LLM、Benchmark 都存到同一个治理型数据库里。

#### 你要重点理解的表

- `agent_task`：任务本体
- `agent_task_event`：任务事件流
- `agent_task_artifact`：任务产物
- `workflow_definition`：工作流定义
- `human_review_action`：人工审核动作
- `learning_plan`：学习计划
- `llm_call_trace`：LLM 调用 trace
- `llm_prompt_version`：prompt 版本
- `mcp_server_config`：MCP server 配置
- `mcp_tool_registry`：MCP 工具注册
- `mcp_tool_approval`：MCP 审批
- `mcp_tool_call_log`：MCP 调用日志
- `skill_plugin`：Skill 插件包
- `skill_registry`：Skill 注册表
- `skill_approval`：Skill 审批
- `skill_execution_log`：Skill 执行日志
- `skill_version_snapshot`：Skill 版本快照
- `plugin_marketplace_install`：Marketplace 安装记录
- `benchmark_run`：Benchmark 运行记录
- `benchmark_result`：Benchmark 结果记录

#### 为什么这一层重要

这个项目的前端能看到：

- 历史任务
- 事件时间线
- 报告
- 审批
- LLM trace
- MCP 调用记录
- Skill 版本
- Benchmark 历史

本质上都来自这里。  
所以理解这个文件，就是理解“项目不是一次性运行，而是全过程留痕”。

#### 关键函数解析

##### `__init__()`

作用：

- 初始化数据库路径
- 创建目录
- 初始化全部表结构

可以把它理解成：
> 系统启动时，先把“事实仓库”搭好。

##### `_init_schema()`

作用：

- 创建所有核心表
- 自动补列
- 确保老数据可升级

这里很重要的一点是：  
它不是“简单建表”，而是考虑了 schema 演进。  
这说明项目已经把“版本兼容”当成架构的一部分。

##### `create_task() / update_task() / append_event() / save_artifact()`

这四个方法构成了任务治理的基础动作：

- 创建任务
- 更新状态
- 写事件
- 存产物

##### `save_workflow() / list_workflows() / get_workflow()`

它们把工作流定义也纳入持久化，而不是只保存在前端 JSON 里。

##### `save_mcp_server() / upsert_mcp_tool() / set_mcp_tool_approval() / save_mcp_call_log()`

这组方法说明 MCP 不是临时调用，而是有完整治理链路的：

- 注册
- 发现
- 启用/禁用
- 审批
- 调用日志

##### `save_prompt_version() / list_prompt_versions() / set_active_prompt_version()`

这说明 prompt 也被当作资产管理，而不是写死在代码里。

##### `save_benchmark_run() / append_benchmark_result() / finish_benchmark_run()`

Benchmark 不是临时脚本，而是可保存、可对比、可复跑的评测系统。

---

### 3.2 前端工作台：不是页面，而是整个系统的控制台

关键文件：

- [web/src/App.tsx](../web/src/App.tsx)
- [web/src/api.ts](../web/src/api.ts)
- [web/src/types.ts](../web/src/types.ts)
- [web/src/main.tsx](../web/src/main.tsx)
- [web/src/styles.css](../web/src/styles.css)

#### 你要补的认知

前端不是“看报告的地方”，而是：

- 任务入口
- 工作流编辑
- 事件查看
- 报告查看
- 历史回放
- LLM 管理
- MCP 管理
- Skills 管理
- Marketplace 安装
- Benchmark 运行

所以它是一个“单页控制台”而不是普通结果页。

#### 你应该重点关注什么

##### `App.tsx`

重点看：

- 页面怎么分区
- 状态怎么在各个面板间流转
- 如何切换 task / workflow / skill / mcp / llm / benchmark
- 如何展示事件流、报告和历史

##### `api.ts`

重点看：

- 后端接口怎么统一封装
- 请求参数怎么做标准化
- 响应如何对齐后端 schema

##### `types.ts`

重点看：

- 前后端数据结构如何对齐
- Task / Event / Artifact / Workflow / Skill / MCP / Benchmark 类型如何统一

##### `styles.css`

这个文件主要负责前端控制台的静态视觉层。当前版本已经收敛为极简风格，因此重点是：

- 统一中性背景和面板边框
- 保留必要的状态色和交互反馈
- 避免额外的背景纹理、渐变和拟物效果
- 保证各页面模块清晰可读

---

### 3.3 RAG：不是检索 demo，而是治理型知识库

关键文件：

- [app/persistence/rag_store.py](../app/persistence/rag_store.py)
- [app/agents/rag_tools.py](../app/agents/rag_tools.py)
- [治理化 RAG 说明](亮点补充/治理化 RAG（区别于 Demo 级简易检索）.md)

#### 你要补的核心认识

RAG 在这里不是“把文档切块然后向量检索”这么简单，而是：

- 文档版本化
- 当前版本与历史版本共存
- ACL 控制
- chunk 与 document 分层
- 混合检索
- rerank
- Gold Set 评测

#### `rag_store.py` 的关键设计

##### `ingest()`

作用：

- 按文档内容 hash 判断是否变化
- 仅更新变化文件
- 为变化文件生成新版本
- 重建对应 chunk

这意味着：
> RAG 不是每次全量重建，而是增量治理。

##### `query()`

作用：

- 先取当前版本 chunk
- 再做 ACL 过滤
- 再做混合排序
- 再做可选 LLM rerank

##### `set_document_acl()`

作用：

- 给文档设置访问控制

这说明知识库不是默认全开放的。

##### `save_gold_case() / list_gold_cases()`

作用：

- 维护评测集
- 支持 RAG Recall@K、Precision@K、MRR 这种标准评估

#### 你要理解的架构重点

RAG 的核心不是“查得到”，而是：

- 能版本化
- 能限制访问
- 能评测
- 能升级
- 能回溯

---

### 3.4 Memory：长期记忆与 RAG 是两套系统

关键文件：

- [app/persistence/memory_store.py](../app/persistence/memory_store.py)
- [app/persistence/memory_store.py](../app/persistence/memory_store.py)

#### 你要补的核心认识

Memory 存的不是项目知识，而是：

- 用户偏好
- 稳定的项目事实
- 团队约定

它和 RAG 的区别非常重要：

- RAG 处理“知识内容”
- Memory 处理“长期有效的记忆”

#### `memory_store.py` 的关键流程

##### `extract_candidates()`

作用：

- 从文本中抽取候选记忆
- 区分 `user / project / team`
- 去重
- 检查冲突
- 写入候选记录

##### `_extract_memory_candidates()`

作用：

- 先尝试 LLM 抽取
- LLM 不可用时再回退规则抽取

##### `confirm()`

作用：

- 把候选记忆确认成正式记忆
- 如果有冲突，把旧记忆标成 superseded

##### `expire_due_memories()`

作用：

- 把到期记忆自动降级为 expired

##### `reject() / delete()`

作用：

- 拒绝或彻底删除记忆

#### 你要重点理解的流程

```text
用户输入
  -> 候选抽取
  -> 去重
  -> 冲突检测
  -> 质量评分
  -> 用户确认
  -> 进入长期记忆
  -> 到期或删除
```

---

### 3.5 Skill：不是函数，是受治理的能力单元

关键文件：

- [app/skills/base.py](../app/skills/base.py)
- [app/skills/contract.py](../app/skills/contract.py)
- [app/skills/builtin.py](../app/skills/builtin.py)
- [app/skills/registry.py](../app/skills/registry.py)
- [app/skills/executor.py](../app/skills/executor.py)
- [app/skills/sandbox.py](../app/skills/sandbox.py)
- [app/marketplace/installer.py](../app/marketplace/installer.py)
- [app/marketplace/catalog.py](../app/marketplace/catalog.py)

#### 你要补的完整链路

```text
SKILL.md / plugin.json
  -> Marketplace 安装
  -> 合约校验
  -> Skill Registry
  -> 审批
  -> Executor
  -> Sandbox
  -> Execution Log
```

#### 关键概念

##### `SkillRegistry`

作用：

- 收纳内置 Skill
- 通过 `skill_code` 找 Skill
- 提供统一执行接口

##### `execute_skill()`

作用：

- 查数据库中的 Skill
- 检查启用状态
- 检查审批
- 校验合约
- 检查依赖
- 合并默认输入和外部输入
- 执行并写日志

##### `validate_skill_contract()`

作用：

- 校验 `execution_type`
- 校验 `permissions`
- 校验 `dependencies`
- 校验 `entrypoint`

##### `run_python_skill_sandbox()`

作用：

- 把 python Skill 放进隔离环境执行

这说明：
> 代码型 Skill 不是“直接在主进程跑”，而是受沙箱保护的。

##### `marketplace/installer.py`

作用：

- 接收外部插件包
- 支持 `plugin.json`
- 支持外部 `SKILL.md`
- 把外部 Skill 转成系统内部资源

#### 最重要的审批模型

```text
approval key = skill_code + agent_code
```

同一个 Skill：

- `skill_console` 的审批，不代表 `workflow_runner` 的审批
- 手动测试和工作流自动执行，是两套身份

这是企业级插件治理非常重要的设计。

---

### 3.6 MCP：本地适配器和真协议客户端是两条线
#### [[MCP 外部工具 与项目工具的理解]]
#### [[本地适配器：LocalMCPProvider 与真协议客户端：RealMCPProvider]]

关键文件：

- [app/providers/mcp_provider.py](../app/providers/mcp_provider.py)
- [scripts/launch_mcp_filesystem.py](../scripts/launch_mcp_filesystem.py)
- [scripts/launch_mcp_memory.py](../scripts/launch_mcp_memory.py)
- [scripts/fake_mcp_server.py](../scripts/fake_mcp_server.py)

#### 你要补的核心认知 [[Jaycode/docs/亮点补充/mcp_provider.py 整个项目的工具接入中枢]]

项目里 MCP 不是单一实现，而是两层：

- `LocalMCPProvider`
  - 本地确定性适配器
  - 用于开发、演示和回退
- `RealMCPProvider`
  - 真正的 stdio MCP client
  - 支持 server 配置、工具发现、调用、日志、审批

#### `LocalMCPProvider` 的职责

- 列文件
- 读文件
- 列目录
- 搜索文件
- git status
- git log

#### `RealMCPProvider` 的职责

- 管理 server 配置
- 发现工具
- 保存工具注册
- 设置工具审批
- 调用工具
- 保存调用日志

#### 你要理解的治理点

MCP 工具不是“谁都能直接调”：

- 先注册
- 再启用
- 再审批
- 再调用
- 全程留日志

这和 Skill 的治理思路是一致的。



---

### 3.7 LLM Provider：模型治理而不是简单调用

关键文件：

- [app/providers/llm_provider.py](../app/providers/llm_provider.py)
- [Harness Runtime 说明](亮点补充/Harness Runtime.md)

#### 你要补的核心认知

这个项目把 prompt、模型、trace、fallback 都当成了可管理资产。

#### `LLMProvider` 的关键职责

- 读取 `.env`
- 支持 per-agent 模型配置
- 管理 prompt 版本
- 记录 trace
- 支持 fallback
- 支持 A/B 比较
- 汇总 token / cost / latency

#### 关键方法

##### `generate_with_status()`

作用：

- 解析 prompt 版本
- 读取模型配置
- 没有 API Key 时走 fallback
- 调用真实模型
- 保存 trace

##### `plan_steps()`

作用：

- 给 planner 生成步骤拆解

##### `write_report()`

作用：

- 给 reporter 生成结构化报告

##### `status()`

作用：

- 给前端展示当前 LLM 状态

#### 你要理解的本质

这个项目的 LLM 层不是“调用 OpenAI API”那么简单，而是：

- prompt 版本化
- 模型配置化
- trace 化
- 可回退
- 可统计
- 可比较

---

### 3.8 Benchmark：从“能跑”走向“可量化改进”

关键文件：

- [app/benchmark_runner.py](../app/benchmark_runner.py)
- [Jaycode 架构讲解](Jaycode架构讲解.md)
- [Jaycode 架构讲解](Jaycode架构讲解.md)

#### 你要补的核心认知

Benchmark 不是附属功能，而是这套平台能否持续进化的关键。

#### 主要评测维度

- LLM
- RAG
- Workflow
- MCP
- 多 Agent 协作

#### 常见指标

- 成功率
- 平均延迟
- P95 延迟
- 失败数
- Recall@K
- Precision@K
- MRR
- token / cost

#### 你要理解的架构意义

有 benchmark，系统才能：

- 比较版本
- 验证优化
- 回归测试
- 量化改进

---

### 3.9 Learning / Collaboration：产品化辅助能力

关键文件：

- [app/agents/learning_tools.py](../app/agents/learning_tools.py)
- [app/agents/collaboration_tools.py](../app/agents/collaboration_tools.py)
- [app/graphs/collaboration_runner.py](../app/graphs/collaboration_runner.py)

#### 这些模块在做什么

它们说明这个平台不是只做“技术分析工具”，还在做：

- 学习辅导
- 多 Agent 汇总
- 协作解释
- 结果归纳

#### 为什么要学它们

因为它们和主流程共用同一套治理体系：

- task
- event
- artifact
- report
- review

这说明平台能力不是散落的，而是被统一进同一条任务链。

---

## 4. 关键代码结构图：你后面学习时要怎么串

### 4.1 任务创建与运行链

```text
前端提交任务
  -> routes.py 接收请求
  -> harness.runtime.create_context()
  -> SQLiteTaskStore.create_task()
  -> harness.runtime.run_graph()
  -> graph.invoke(...)
  -> save_artifact / update_task / append_event
  -> 返回 result / report / events
```

### 4.2 项目分析链

```text
project_path
  -> scan_project()
  -> identify_tech_stack()
  -> analyze_modules()
  -> extract_api_hints()
  -> generate_findings()
  -> quality_score()
  -> generate_report()
```

### 4.3 代码审查链

```text
project_path
  -> scan_project()
  -> review_project()
  -> review_single_file()
  -> _review_file()
  -> _infer_responsibilities()
  -> _extract_dependencies()
  -> _build_call_chain_context()
  -> _assess_testability()
  -> _semantic_file_review()
  -> _file_report()
```

### 4.4 Skill 执行链

```text
skill_code
  -> task_store.get_skill()
  -> skill approval
  -> validate_skill_contract()
  -> dependency check
  -> registry.execute() / declarative execute
  -> sandbox or prompt call
  -> skill execution log
```

### 4.5 RAG 链

```text
project_path
  -> scan_project()
  -> process_knowledge()
  -> chunk_text()
  -> keywords()
  -> faq()
  -> rag_store.ingest()
  -> rag_store.query()
  -> ACL + hybrid retrieval + rerank
```

### 4.6 Memory 链

```text
user message
  -> extract_candidates()
  -> LLM / rule extraction
  -> conflict detection
  -> quality governance
  -> confirm / reject / delete
  -> expire_due_memories()
```

### 4.7 Workflow 编译链

```text
workflow JSON
  -> validate_workflow_definition()
  -> compile_workflow_graph()
  -> _node_runner()
  -> _execute_node()
  -> run_compiled_workflow()
  -> resume_task_workflow()
```

---

## 5. 你还应该重点读的文档

除了代码，下面这些文档非常值得补：

- [Jaycode 架构讲解](Jaycode架构讲解.md)
- [Jaycode 架构讲解](Jaycode架构讲解.md)
- [Harness Runtime 说明](亮点补充/Harness Runtime.md)
- [Jaycode 使用说明](Jaycode使用说明.md)
- [编排页面说明](亮点补充/编排页面.md)
- [编排页面说明](亮点补充/编排页面.md)
- [治理化 RAG 说明](亮点补充/治理化 RAG（区别于 Demo 级简易检索）.md)
- [Jaycode 架构讲解](Jaycode架构讲解.md)

这些文档的价值在于：

- 告诉你每一阶段为什么这么做
- 告诉你每个架构决策是怎么演进出来的
- 告诉你哪个能力是 MVP，哪个是生产化补强

---

## 6. 按优先级给你的补学建议

### 第一优先级：必须掌握

1. [app/persistence/sqlite_store.py](../app/persistence/sqlite_store.py)
2. [app/skills/contract.py](../app/skills/contract.py)
3. [app/skills/executor.py](../app/skills/executor.py)
4. [app/providers/llm_provider.py](../app/providers/llm_provider.py)
5. [app/persistence/rag_store.py](../app/persistence/rag_store.py)
6. [app/persistence/memory_store.py](../app/persistence/memory_store.py)

### 第二优先级：强烈建议掌握

1. [web/src/App.tsx](../web/src/App.tsx)
2. [app/providers/mcp_provider.py](../app/providers/mcp_provider.py)
3. [app/marketplace/installer.py](../app/marketplace/installer.py)
4. [app/benchmark_runner.py](../app/benchmark_runner.py)
5. [app/agents/learning_tools.py](../app/agents/learning_tools.py)
6. [app/agents/collaboration_tools.py](../app/agents/collaboration_tools.py)

### 第三优先级：后续补充

1. [web/src/styles.css](../web/src/styles.css)
3. [scripts/launch_mcp_filesystem.py](../scripts/launch_mcp_filesystem.py)
4. [scripts/launch_mcp_memory.py](../scripts/launch_mcp_memory.py)
5. [scripts/fake_mcp_server.py](../scripts/fake_mcp_server.py)

---

## 7. 你要形成的学习心智模型

### 7.1 不要把它看成“一个 Agent 项目”

更准确地说，它是一个：

- 多 Agent 平台
- 任务治理系统
- 可编排工作流引擎
- 可治理知识库
- 可治理长期记忆系统
- 可插拔 Skill 平台
- 可观测 LLM 平台
- 可量化 Benchmark 平台

### 7.2 不要把 Skill、MCP、LLM、RAG 混成一类

它们的职责不同：

- `Skill`：平台内的可治理能力单元
- `MCP`：外部工具协议和工具接入
- `LLM`：通用推理和生成能力
- `RAG`：项目知识检索与治理

### 7.3 不要把 Runtime 当成“多包一层”

`harness.runtime` 的意义不是封装调用，而是：

- 任务状态管理
- 事件时间线
- 产物留痕
- 审核和恢复
- 治理信息沉淀

---

## 8. 这阶段学完后，你应该能回答的问题

如果你已经把这份补充手册看懂了，至少应该能比较清楚地回答这些问题：

### 1. 事实数据和运行记录存在哪里？

#### 知识点

- 项目不是把所有数据都放在一个地方。
- 运行事实、任务过程、审批记录、工具调用日志主要放在 SQLite 治理库里。
- 长期记忆候选单独放在 memory 系统里。
- 项目知识文档和检索切片放在 RAG 系统里。

#### 讲解

这个项目的数据是“分层存放”的，不同层负责不同职责。  
`sqlite_store` 更像“平台事实仓库”，保存的是任务、事件、工作流、Skill、MCP server、MCP 审批、调用日志这些运行时事实。  
`memory_store` 不是任务日志，而是长期记忆候选，比如偏好、项目事实、团队规则。  
`rag_store` 则是知识库，存的是文档、切片、检索内容，用于查询和召回。

#### 项目落点

- [app/persistence/sqlite_store.py](../app/persistence/sqlite_store.py)
- [app/persistence/memory_store.py](../app/persistence/memory_store.py)
- [app/persistence/rag_store.py](../app/persistence/rag_store.py)

#### 记忆方式

- `sqlite_store`：事实与治理
- `memory_store`：长期记忆
- `rag_store`：知识检索

---

### 2. 为什么 Skill 不是普通函数？

#### 知识点

- Skill 是平台托管的能力，不只是代码里的一个函数。
- Skill 有权限、版本、依赖、输入输出 schema、审批、测试和执行日志。
- 普通函数只负责“执行动作”，Skill 还负责“治理动作”。

#### 讲解

普通函数是“写了就直接调用”，而 Skill 是“先被平台登记，再被平台批准，再被平台执行”。  
比如一个 Skill 要求读文件或调用工具，它不仅要能干活，还要说明自己需要什么权限、输入格式是什么、输出格式是什么。  
这样做的好处是：Skill 可以被复用、被审查、被回滚、被测试，也能在工作流和 Skills 页面中统一使用。

#### 项目落点

- [app/skills/executor.py](../app/skills/executor.py)
- [app/skills/builtin.py](../app/skills/builtin.py)

#### 记忆方式

- 普通函数 = 做事
- Skill = 做事 + 被平台治理

---

### 3. 为什么同一个 Skill 要按 `skill_code + agent_code` 审批？

#### 知识点

- 审批不是只看 Skill 名字。
- 还要看“谁在调用它”。
- `skill_code` 决定能力，`agent_code` 决定身份。

#### 讲解

同一个 Skill 在不同场景下，风险是不同的。  
比如 `skill_console` 是人在 Skills 页面上手动测试，`workflow_runner` 是工作流自动执行，这两个身份的风险完全不一样。  
所以系统必须按 `skill_code + agent_code` 精确匹配审批，不能只要一个审批通过就全部放行。  
这样做是为了防止测试权限自动泄露到生产执行身份。

#### 项目落点

- [app/persistence/sqlite_store.py](../app/persistence/sqlite_store.py)
- [web/src/App.tsx](../web/src/App.tsx)

#### 记忆方式

- `skill_code` = 干什么
- `agent_code` = 谁来干
- 审批必须两者一起看

---

### 4. 为什么 RAG 和 Memory 是两套系统？

#### 知识点

- RAG 是知识检索系统。
- Memory 是长期记忆系统。
- 一个偏“找资料”，一个偏“存经验”。

#### 讲解

RAG 的目标是“把项目资料找回来”，所以它更像文档库和知识库。  
Memory 的目标是“把值得长期保留的经验保存下来”，比如用户偏好、项目规则、团队约定。  
Memory 不是直接把聊天原文全存进去，而是先提取候选、再确认、再保存。  
这两个系统虽然都处理知识，但一个解决“检索”，一个解决“记忆”，不能混成一套。

#### 项目落点

- [app/persistence/rag_store.py](../app/persistence/rag_store.py)
- [app/persistence/memory_store.py](../app/persistence/memory_store.py)

#### 记忆方式

- RAG = 文档检索
- Memory = 长期记忆

---

### 5. 为什么 LLM provider 要保存 prompt 版本和 trace？

#### 知识点

- LLM 不只是“返回答案”。
- 它还要可追踪、可复现、可比较。
- prompt 版本和 trace 是治理基础。

#### 讲解

如果没有 prompt 版本，你很难知道某次回答为什么变了。  
如果没有 trace，你很难回溯一次调用到底用了什么输入、什么模型、返回了什么结果。  
这个项目把 prompt 版本、模型配置、token 消耗、成本、fallback 记录都保留下来，就是为了让 LLM 行为可审计。  
这对于 Agent 平台很重要，因为 Agent 的行为不是一次性输出，而是长期运行、长期迭代的。

#### 项目落点

- [app/providers/llm_provider.py](../app/providers/llm_provider.py)
- [app/persistence/sqlite_store.py](../app/persistence/sqlite_store.py)

#### 记忆方式

- prompt 版本 = 用了哪套提示词
- trace = 这次调用的全过程
- token/cost = 运行成本和规模

---

### 6. 为什么 MCP 既有本地适配器，又有真实 stdio client？

#### 知识点

- MCP 有两条实现线。
- `LocalMCPProvider` 是本地适配器。
- `RealMCPProvider` 是真实协议客户端。
- `MCPProvider` 是统一门面。

#### 讲解

本地适配器是为了默认可用，不依赖外部 server，也能读文件、列目录、查 Git。  
真实 client 则是为了接入外部 MCP Server，通过 stdio JSON-RPC 真实调用工具。  
这两条线不是重复，而是“本地可跑”和“外部可接”两种阶段的解决方案。  
项目通过环境变量决定走哪条线，因此上层代码不用关心底层实现是本地还是远程。

#### 项目落点

- [app/providers/mcp_provider.py](../app/providers/mcp_provider.py)

#### 记忆方式

- local = 本地默认
- real = 外部协议接入
- provider = 统一入口

---

### 7. 为什么 Workflow 要先 validate、再 compile、再 run、再 resume？

#### 知识点

- Workflow 不是脚本，而是图。
- 图要先检查合法性，再转成可执行逻辑。
- 中断后还要能恢复。

#### 讲解

`validate` 是为了防止错误的图、错误的配置直接运行。  
`compile` 是把可视化工作流转成真正能执行的 LangGraph 逻辑。  
`run` 才是执行过程，而不是一开始就直接跑。  
如果流程中有人工审核或异常中断，还需要 `resume` 从断点继续，这体现了治理型工作流的设计思想。

#### 项目落点

- [app/graphs/workflow_compiler.py](../app/graphs/workflow_compiler.py)
- [app/harness/runtime.py](../app/harness/runtime.py)

#### 记忆方式

- validate = 检查图
- compile = 生成执行逻辑
- run = 正式运行
- resume = 从断点恢复

---

### 8. 为什么前端是工作台，不是结果页？

#### 知识点

- 前端是操作台，不是静态展示页。
- 它承载任务、聊天、Skill、MCP、LLM、Benchmark、Marketplace 等多个功能区。
- 重点是“协作”和“治理”，不是只看结果。

#### 讲解

这个项目的前端不是简单的报告展示，而是整个系统的人机交互中心。  
你可以在前端发起任务、切换工作流、查看聊天、审批 Skill、管理 MCP、看 LLM trace、跑 benchmark。  
这说明前端不是最终输出页，而是整个平台的“工作台”。  
它的作用是让人参与整个 Agent 运行过程，而不是只等结果。

#### 项目落点

- [web/src/App.tsx](../web/src/App.tsx)
- [web/src/styles.css](../web/src/styles.css)

#### 记忆方式

- 工作台 = 操作和协作入口
- 结果页 = 只看输出
- 这个项目明显是前者

---

### 9. 为什么 benchmark 是平台能力的一部分？

#### 知识点

- benchmark 不只是测试附件。
- 它是平台治理的一部分。
- 用来衡量能力是否稳定、是否回归、是否可比较。

#### 讲解

Agent 平台不能只看“能不能跑”，还要看“跑得好不好”。  
benchmark 会覆盖 LLM、RAG、Workflow、MCP、多 Agent 协作等多个方向，说明这个平台不是只做功能，而是也做评测。  
有了 benchmark，系统改动后可以比较新旧表现，也能发现性能、准确率、召回率、延迟等问题。  
所以 benchmark 不是附属页面，而是平台持续演进的一部分。

#### 项目落点

- [app/benchmark_runner.py](../app/benchmark_runner.py)
- [app/api/routes.py](../app/api/routes.py)

#### 记忆方式

- benchmark = 评测能力
- 评测 = 平台治理的一部分

---

### 10. 为什么这个项目适合做企业级 Agent 平台参考实现？

#### 知识点

- 它不是单一聊天工具。
- 它是一个完整的 Agent 平台样例。
- 强调执行、治理、审计、扩展和评测。

#### 讲解

企业级平台最关心的不是“能不能回答一句话”，而是“能不能稳定跑任务、能不能管权限、能不能审计、能不能恢复、能不能评测”。  
这个项目把任务、工作流、Skill、RAG、Memory、MCP、审批、日志、benchmark 全部串起来了。  
它展示的是一套可扩展的 Agent 平台思路，而不只是某一个功能模块。  
所以它适合拿来学习“企业级 Agent 平台应该怎么分层、怎么治理、怎么留痕”。

### 项目落点

- [README.md](../README.md)
- [app/persistence/sqlite_store.py](../app/persistence/sqlite_store.py)
- [app/providers/mcp_provider.py](../app/providers/mcp_provider.py)
- [app/skills/executor.py](../app/skills/executor.py)

### 记忆方式

- 能跑
- 能管
- 能审
- 能扩
- 能测

---

## 9. 学习结论

Jaycode 的价值，不在某一个单点功能，而在于它把一整套 Agent 平台能力串了起来：

- 有能力层
- 有编排层
- 有治理层
- 有持久化层
- 有可观测层
- 有前端工作台
- 有插件扩展
- 有 benchmark 评测

如果你想系统学习 Agent 开发，这个项目比“单纯的聊天 Demo”更值得深挖，因为它更接近真实工程形态。
