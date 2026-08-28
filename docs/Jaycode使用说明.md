# Jaycode 前端详细使用手册

## 1. 文档定位

这份手册用于指导你实际使用 Jaycode Web 控制台。

它会说明：

- Jaycode 前端如何启动
- 页面各个区域的作用
- 如何创建和运行任务
- 如何使用 Agent、Workflow、Planner、Collab、Tool、Knowledge 模式
- 如何编排和保存 Workflow
- 如何查看事件、报告、历史和恢复状态
- 如何使用 LLM、MCP、Skills、Marketplace、RAG 和 Benchmark
- 遇到页面异常时如何排查

Jaycode 前端不是单纯的展示页面，而是一个围绕“任务、执行、治理、结果”的操作工作台。

最核心的使用闭环是：

```text
填写任务目标
  -> 选择项目路径
  -> 选择运行模式
  -> 启动任务
  -> 查看事件流
  -> 处理人工审核
  -> 查看报告
  -> 追问或恢复任务
  -> 保存知识、技能或评测结果
```

---

## 2. 启动前准备

### 2.1 启动后端和前端

最简单的启动方式：

```powershell
cd F:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

然后打开：

```text
http://127.0.0.1:8100/
```

推荐使用一键启动：

```powershell
cd F:\JayAgent\Jaycode
powershell -ExecutionPolicy Bypass -File .\setup-and-start.ps1
```

一键启动通常会完成：

1. 检查 `.env`
2. 检查 Python 环境
3. 安装 Python 依赖
4. 检查 Node.js 和 npm
5. 安装 Web 依赖
6. 构建 `web/dist`
7. 启动 FastAPI
8. 通过 FastAPI 托管 React 控制台

### 2.2 前端单独开发模式

如果你需要修改 React 页面，可以单独启动 Vite：

```powershell
cd F:\JayAgent\Jaycode\web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173/
```

开发模式下，后端仍然必须运行在：

```text
http://127.0.0.1:8100/
```

因为任务、技能、Marketplace、RAG 和 Benchmark 数据都来自 FastAPI API。

### 2.3 如何确认启动成功

检查后端：

```text
http://127.0.0.1:8100/health
```

检查 API 文档：

```text
http://127.0.0.1:8100/docs
```

检查前端产物：

```powershell
Test-Path F:\JayAgent\Jaycode\web\dist\index.html
Test-Path F:\JayAgent\Jaycode\web\dist\assets\jaycode.css
```

如果页面能打开但没有样式，通常说明 `jaycode.css` 没有加载，或者浏览器打开的是旧缓存。

---

## 3. 页面整体布局

Jaycode 控制台主要由四部分组成：

```text
左侧导航
  -> 页面模块切换

页面左侧操作面板
  -> 输入参数、选择对象、发起动作

页面中间过程面板
  -> 查看事件、日志、列表或执行过程

页面右侧详情面板
  -> 查看当前选中任务、技能、安装包或评测结果
```

在运行页中，最常见的布局是：

```text
运行入口 | 执行事件 | 当前状态
```

这三个区域分别对应：

- 运行入口：告诉 Jaycode 要做什么
- 执行事件：告诉你 Jaycode 正在做什么
- 当前状态：告诉你当前任务最终处于什么状态

---

## 4. 左侧导航栏

### 4.1 运行

运行是最常用的页面。

功能包括：

- 创建任务
- 选择执行模式
- 设置项目目录
- 设置扫描文件数
- 设置人工审核
- 运行当前 Workflow
- 查看实时事件
- 查看当前任务状态
- 查看 Resume 信息

建议第一次使用时从这里开始。

### 4.2 编排

编排页面用于创建和修改可执行 Workflow。

功能包括：

- 查看已有 Workflow
- 创建新的 Workflow
- 从节点面板添加节点
- 拖动节点位置
- 连接节点
- 修改节点参数
- 校验 Workflow
- 保存 Workflow
- 更新已有 Workflow

编排页面不是纯画图工具。画布上的节点和连线会直接影响 Workflow 模式的实际执行。

### 4.3 报告

报告页面用于查看任务的最终输出。

通常包括：

- 最终报告
- 项目分析结论
- 风险信息
- 重构建议
- 下一步行动
- Mermaid 流程图
- 治理信息
- 结构化 finding

报告页适合在任务执行完成后使用。

### 4.4 追问

追问页面用于继续询问当前任务。

可以使用三种方向：

- 任务追问：围绕当前任务和报告提问
- 知识查询：从 RAG 知识库检索
- 学习陪练：围绕项目学习继续提问

适合的问题：

```text
这个项目最重要的入口在哪里？
刚才的代码审查为什么判定为高风险？
这个 Workflow 为什么停在人工审核？
下一步应该先修改哪个模块？
```

### 4.5 历史

历史页面用于查看持久化任务。

可以查看：

- 历史任务列表
- 任务状态
- 任务目标
- 项目路径
- 创建时间
- 更新时间
- 任务事件
- 任务产物
- 恢复记录

历史页适合排查“之前发生过什么”。

### 4.6 LLM

LLM 页面用于查看模型治理和调用信息。

主要功能：

- 查看 LLM trace
- 查看调用模型
- 查看提示词版本
- 查看调用耗时
- 查看 token 使用
- 查看 fallback 情况
- 查看估算成本
- 设置激活的 prompt 版本
- 运行 prompt A/B 测试

如果你发现某次结果和之前不同，可以到这里检查：

1. 使用的模型是否变化
2. Prompt 版本是否变化
3. 是否使用了 fallback
4. 调用是否报错
5. 输入输出 token 是否异常

### 4.7 MCP

MCP 页面用于管理外部工具。

包括：

- MCP Provider 状态
- MCP Server 配置
- Server 启用/停用
- 工具发现
- 工具启用/停用
- 工具审批
- 工具调用
- 工具调用日志

MCP 的基本流程是：

```text
保存 Server
  -> 启用 Server
  -> Discover Tools
  -> 审批 Tool
  -> 调用 Tool
  -> 查看调用日志
```

### 4.8 Skills

Skills 页面用于管理 Jaycode 的技能。

可以查看：

- Skill Plugin
- Skill 列表
- Skill 详情
- Skill 版本
- Skill 权限
- Skill 依赖
- Skill 审批
- Skill 执行日志
- Skill 测试结果

Skills 页面适合确认一个技能是否可以安全执行。

### 4.9 Market

Market 页面用于安装外部能力包。

支持查看：

- 包目录
- 包名称
- 包类型
- 包版本
- 包描述
- 包权限
- 包依赖
- 包预览
- 安装记录
- 卸载记录

Marketplace 是“能力分发和安装系统”，Skills 是“具体可执行能力”。

### 4.10 Bench

Bench 页面用于运行和查看 Benchmark。

可以查看：

- Benchmark 类型
- 历史运行
- 成功率
- 平均耗时
- P95 耗时
- 失败数量
- 质量评分
- baseline
- threshold
- regression
- 历史趋势

Benchmark 用来判断修改之后系统是变好了还是变差了。

---

## 5. 运行页详细使用

## 5.1 Agent 模式

Agent 模式适合快速执行一个常规任务。

典型流程：

```text
任务目标
  -> Planner
  -> Project Analyzer
  -> Reporter
```

适合：

- 项目概览
- 简单项目分析
- 快速查看报告

不适合：

- 需要自定义复杂节点顺序的任务
- 需要精确控制每个节点配置的任务

## 5.2 Workflow 模式

Workflow 模式会使用当前画布中的节点和连线。

适合：

- 自己定义执行流程
- 加入人工审核
- 插入 Skill
- 插入 MCP 工具
- 插入 RAG 查询
- 让某些节点并行或按条件执行

选择 Workflow 后，点击：

```text
运行当前画布
```

系统会根据当前保存或编辑中的画布执行。

## 5.3 Planner 模式

Planner 模式会先根据任务目标生成 Workflow，再执行生成的流程。

适合：

- 不想手动搭建流程
- 想让系统根据目标自动选择节点
- 想快速验证自动规划能力

流程通常是：

```text
目标
  -> Planner 自动生成 Workflow
  -> 校验 Workflow
  -> 执行 Workflow
  -> 生成报告
```

## 5.4 Collab 模式

Collab 模式用于多 Agent 协作。

常见流程包含：

- Planner
- Project Analyzer
- Code Reviewer
- RAG Processor
- Supervisor
- Reporter

适合：

- 需要多角度分析项目
- 需要同时做架构、代码、知识和风险分析
- 需要 Supervisor 汇总多个 Agent 输出

## 5.5 Tool 模式

Tool 模式偏向工具调用。

适合：

- 查询文件
- 执行已审批的 MCP 工具
- 验证工具调用链

使用前要确认：

- MCP Server 已启用
- 工具已发现
- 工具已审批

## 5.6 Knowledge 模式

Knowledge 模式用于知识检索。

适合：

- 查询项目知识
- 检索已经保存的笔记
- 查询项目文档
- 使用 RAG 辅助任务

如果知识库没有内容，先在报告页或追问页保存知识笔记，再执行查询。

---

## 6. 运行页输入项

### 6.1 任务目标

任务目标决定整个执行方向。

推荐写法：

```text
分析这个项目的架构，并列出最需要重构的三个模块
```

不推荐写法：

```text
看看
```

目标越具体，Planner 越容易生成合适的流程。

### 6.2 项目路径

项目路径必须是后端可以访问的本地目录。

例如：

```text
F:/JayAgent/Jaycode
```

建议使用正斜杠，或者使用完整 Windows 路径：

```text
F:\JayAgent\Jaycode
```

### 6.3 最大扫描文件数

这个值限制项目分析最多读取多少文件。

建议：

| 项目规模 | 建议值 |
|---|---:|
| 小型项目 | 50 - 100 |
| 中型项目 | 100 - 300 |
| 大型项目 | 300 - 800 |

如果设置太小，可能只扫描到入口文件，分析结果会不完整。

### 6.4 人工审核

打开后，Workflow 遇到审核节点会进入：

```text
waiting_review
```

这时任务不会自动结束，需要你在审核区执行：

- approve
- reject
- revise

## 7. 事件流详细说明

中间的执行事件区域是排查任务的核心。

### 7.1 任务事件

```text
task runtime created
task runtime running
task runtime completed
```

表示任务生命周期。

### 7.2 节点事件

```text
plan planner running
review human_review running
report reporter completed
```

表示某个 Workflow 节点的生命周期。

### 7.3 审核事件

```text
review human_review waiting_review
```

表示任务等待人工决定。

### 7.4 恢复事件

```text
workflow_resume harness_runtime running
```

表示系统从某个 checkpoint 恢复执行。

### 7.5 如何定位失败

如果任务失败：

1. 找到最后一个 `running` 事件
2. 查看后面是否出现 `failed`
3. 查看事件详情中的错误信息
4. 确认是参数、权限、Provider 还是代码错误

---

## 8. Workflow 编排详细使用

### 8.1 节点类型

当前常见节点包括：

- `Planner`
- `Project Agent`
- `Code Review`
- `File Review`
- `RAG Processor`
- `Knowledge Query`
- `MCP Tool`
- `Skill`
- `Supervisor`
- `Human Review`
- `Reporter`

### 8.2 推荐的基础流程

```text
Planner
  -> Project Agent
  -> Human Review
  -> Reporter
```

### 8.3 推荐的代码审查流程

```text
Planner
  -> Project Agent
  -> Code Review
  -> Human Review
  -> Reporter
```

### 8.4 推荐的知识沉淀流程

```text
Planner
  -> Project Agent
  -> RAG Processor
  -> Reporter
```

### 8.5 添加节点

一般操作步骤：

1. 在节点面板选择节点
2. 拖动到画布
3. 修改节点名称
4. 修改节点配置
5. 用连接点连接前后节点
6. 执行 Workflow 校验
7. 保存 Workflow

### 8.6 Skill 节点

Skill 节点至少要确认：

- `skill_code`
- `agent_code`
- Skill 是否启用
- 当前调用身份是否审批

Workflow 自动执行 Skill 时，通常使用：

```text
workflow_runner
```

### 8.7 MCP Tool 节点

MCP Tool 节点需要确认：

- `server_id`
- `tool_name`
- 工具是否已 discover
- 工具是否启用
- `agent_code` 是否审批

### 8.8 Human Review 节点

Human Review 节点用于暂停流程，等待人工决定。

适合放在：

- 代码修改前
- 外部工具调用前
- 高风险操作前
- 报告归档前

### 8.9 Reporter 节点

Reporter 通常放在流程末尾，用于合并前面节点的输出并生成最终结果。

---

## 9. 报告、产物和建议

任务完成后，报告页面通常包含：

- 最终报告
- 风险级别
- 建议列表
- 结构化 finding
- 下一步行动
- 工具调用信息
- Agent 输出
- Mermaid 流程图

建议阅读顺序：

1. 先看风险等级
2. 再看最终报告
3. 再看结构化建议
4. 最后看 Mermaid 和事件流

如果要继续执行，可以把“下一步行动”复制成新的任务目标。

---

## 10. 追问、知识库和学习陪练

### 10.1 任务追问

任务追问会结合当前任务的报告和事件。

适合：

```text
这个问题对应哪些文件？
为什么把这个模块判定为高风险？
如果不重构会有什么影响？
```

### 10.2 RAG 知识查询

知识查询会从指定集合中检索内容。

常见集合：

```text
project-memory
```

适合查询：

- 项目结构
- 已保存的架构笔记
- 历史结论
- 模块说明

### 10.3 保存知识笔记

可以把人工判断、架构说明、项目规则保存到知识库。

建议保存：

- 重要模块说明
- 团队约定
- 已确认的技术决策
- 高频问题的答案

### 10.4 学习陪练

学习陪练适合帮助你理解项目。

可以询问：

- 这个模块应该先看什么
- 这个文件为什么放在这一层
- Service 和 Harness 的区别
- 一个任务从 API 到 Runtime 怎么走

---

## 11. 历史、审核和 Resume

### 11.1 历史任务

历史页面可以选择任务并加载：

- 任务详情
- 事件
- Artifact
- Report
- Resume Snapshot

### 11.2 审核任务

当任务状态为：

```text
waiting_review
```

说明执行暂停了。

你需要：

1. 查看审核问题
2. 查看当前节点输出
3. 输入审核意见
4. 选择 approve、reject 或 revise

### 11.3 Resume

Resume 表示从之前的 checkpoint 继续。

右侧 Resume 区域重点查看：

- 从哪个节点恢复
- 审核动作是什么
- 恢复前状态
- 恢复后新增事件
- 恢复结果

如果 Resume 后没有新事件，通常说明恢复动作没有真正触发或后端执行失败。

---

## 12. LLM 页面详细使用

### 12.1 Traces

查看每次模型调用：

- Agent
- Prompt 版本
- Model
- Latency
- Token Usage
- Fallback
- Error

### 12.2 Prompts

查看不同 Agent 的提示词版本。

可以确认：

- 当前激活版本
- Prompt family
- 自定义 Prompt
- 更新时间

### 12.3 Usage

查看：

- 调用次数
- fallback 次数
- 输入 token
- 输出 token
- 平均耗时
- 估算费用

### 12.4 A/B 测试

可以选择两个 prompt 版本，对同一个问题进行对比。

适合：

- 比较新的 Prompt 是否更好
- 比较回答质量
- 验证模型切换影响

---

## 13. MCP 页面详细使用

### 13.1 保存 Server

配置通常包括：

- server_id
- name
- transport
- command
- args
- env

### 13.2 Discover Tools

保存并启用 Server 后，执行工具发现。

发现成功后，工具会出现在工具列表。

### 13.3 审批工具

工具调用前要确认：

- 工具已经注册
- 工具已经启用
- 当前 `agent_code` 已审批

### 13.4 查看日志

日志中重点看：

- tool_name
- agent_code
- input
- output
- status
- latency
- error_message

---

## 14. Skills 页面详细使用

### 14.1 Skill 列表

查看：

- code
- name
- category
- version
- risk level
- enabled

### 14.2 Skill 详情

查看：

- 输入 schema
- 输出 schema
- 默认输入
- 权限
- 依赖
- 测试
- entrypoint

### 14.3 Skill 审批

审批是按以下组合判断的：

```text
skill_code + agent_code
```

不是只要技能被审批一次，所有 Agent 都能调用。

### 14.4 Skill 执行

执行前确认：

1. Skill 已启用
2. 调用身份已审批
3. 输入 JSON 符合 schema
4. Sandbox 配置可用

### 14.5 Skill 日志

执行日志可以帮助你确认：

- 输入是什么
- 输出是什么
- 执行是否成功
- 执行耗时
- 错误信息

---

## 15. Marketplace 页面详细使用

### 15.1 查看目录

目录中重点查看：

- package_id
- package name
- package type
- version
- source
- permissions
- dependencies

### 15.2 安装前预览

建议先执行预览，确认：

- 包类型
- 版本
- 将要创建的对象
- 需要的权限
- 依赖是否满足

### 15.3 安装包

安装通常会记录：

- install_id
- package_id
- version
- status
- summary
- manifest
- installed_at

### 15.4 卸载和回滚

卸载或回滚后，检查：

- 安装状态
- Skill 是否恢复
- Workflow 是否恢复
- 版本是否恢复
- 安装历史是否一致

---

## 16. Benchmark 页面详细使用

### 16.1 Benchmark 类型

常见类型包括：

- `mcp`
- `llm`
- `rag`
- `workflow`
- `collaboration`

### 16.2 运行评测

运行时通常需要：

- Benchmark 名称
- Agent code
- 迭代次数
- 测试 cases

### 16.3 主要指标

不同类型会有不同指标，常见包括：

- success rate
- average latency
- P95 latency
- failure count
- quality score
- fallback rate
- hit rate
- workflow success rate

### 16.4 baseline 和 threshold

baseline 是用于对比的历史基线。

threshold 是允许的变化范围。

如果本次结果比 baseline 明显变差，就可能触发 regression。

### 16.5 如何看回归

建议按照这个顺序：

1. 选择 Benchmark 类型
2. 查看最近运行
3. 选择某次运行
4. 查看 summary
5. 查看历史对比
6. 查看 regression 状态

---

## 17. 一次完整使用示例

### 目标

分析 Jaycode 项目，并找出架构上最值得优先改进的地方。

### 操作步骤

1. 打开 `运行`
2. 目标填写：

```text
分析这个项目的架构，并列出最需要优先改进的三个模块
```

3. 项目路径填写：

```text
F:/JayAgent/Jaycode
```

4. 最大扫描文件数设置为 `200`
5. 选择 `Workflow`
6. 打开人工审核
7. 点击 `运行当前画布`
8. 在中间事件流查看执行过程
9. 如果状态变成 `waiting_review`，查看审核问题
10. 在右侧或审核区域选择 `approve`
11. 等待 Workflow Resume
12. 进入 `报告`
13. 查看风险和建议
14. 进入 `追问` 继续提问
15. 如果结论值得长期保留，把它保存到 RAG 知识库

---

## 18. 常见问题排查

### 18.1 页面完全没有样式

检查：

```powershell
Test-Path F:\JayAgent\Jaycode\web\dist\index.html
Test-Path F:\JayAgent\Jaycode\web\dist\assets\jaycode.css
```

然后强制刷新浏览器。

### 18.2 页面显示旧内容

处理方法：

1. 强制刷新
2. 清除站点数据
3. 重新构建前端
4. 重新启动后端

### 18.3 页面打开但 API 全部失败

确认后端是否运行：

```text
http://127.0.0.1:8100/health
```

开发模式下还要确认 Vite 代理指向 `8100`。

### 18.4 任务一直等待

检查：

- 是否进入 `waiting_review`
- 是否需要人工 approve
- 是否有 MCP 或 Skill 权限未审批
- 是否节点配置不完整

### 18.5 Skill 执行失败

检查：

- Skill 是否启用
- `skill_code` 是否正确
- `agent_code` 是否审批
- 输入 JSON 是否符合 schema
- Sandbox 是否可用

### 18.6 MCP 工具调用失败

检查：

- MCP Provider 是否正确
- Server 是否启用
- 工具是否 discover
- 工具是否启用
- 工具是否审批
- command 和 args 是否正确

### 18.7 RAG 查不到内容

检查：

- 是否已经写入文档
- collection 是否一致
- 查询词是否过于宽泛
- 文档是否成功切片
- RAG Store 是否正常

### 18.8 Benchmark 没有结果

检查：

- 是否真正执行过 Benchmark
- 测试 cases 是否启用
- Agent code 是否正确
- Provider 是否可用
- 运行记录是否写入 SQLite

---

## 19. 推荐使用习惯

### 初次使用

先完成：

1. 启动后端
2. 打开运行页
3. 使用 Agent 或 Workflow 跑一个简单任务
4. 查看事件流
5. 查看报告

### 学习架构

建议：

1. 运行一个带 Human Review 的 Workflow
2. 看任务如何进入 `waiting_review`
3. 执行 approve
4. 看 Resume 事件
5. 查看历史任务

### 使用外部能力

建议顺序：

1. 先测试 Skills
2. 再测试 Marketplace 安装
3. 再配置 MCP
4. 最后运行 Benchmark

### 调试问题

建议顺序：

1. 看浏览器页面
2. 看后端日志
3. 看任务事件
4. 看 Skill/MCP 日志
5. 看 LLM trace
6. 看 Benchmark 历史

---

## 20. 前端和后端的关系

前端页面本身不直接负责业务执行。

调用链是：

```text
React 页面
  -> web/src/api.ts
  -> FastAPI 路由
  -> app/services
  -> Harness Runtime / Graphs
  -> Agents / Skills / Providers
  -> SQLite / RAG / Benchmark
```

因此：

- 页面显示问题优先检查 `web/`
- API 返回问题优先检查 `app/api/`
- 业务流程问题优先检查 `app/services/`
- 执行状态问题优先检查 `app/harness/`
- 数据不一致优先检查 `app/persistence/`

---

## 21. 最后总结

Jaycode 前端的核心使用方法可以概括为：

```text
运行页负责发起任务
编排页负责定义流程
事件流负责观察执行
状态面板负责查看当前状态
报告页负责查看结果
追问页负责继续分析
历史页负责回放和恢复
LLM 页负责模型治理
MCP 页负责外部工具
Skills 页负责技能生命周期
Market 页负责能力安装
Bench 页负责质量评测
```

最推荐的日常操作路径是：

```text
运行
  -> 查看事件
  -> 处理审核
  -> 查看报告
  -> 追问
  -> 保存知识
  -> 历史回放
```

