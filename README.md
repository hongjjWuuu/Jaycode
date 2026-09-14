# Jaycode

Jaycode 是一个面向软件项目理解、代码审查和工程治理的多 Agent 工作台。

项目使用 FastAPI 提供后端 API，使用 LangGraph 编排 Agent 和 Workflow，并将项目分析、代码审查、RAG 知识库、Skill 插件、MCP 工具、任务运行时、人工审核、历史回放和 Benchmark 评测整合到一个可视化工作台中。

## 项目定位

Jaycode 不只是一个简单的聊天机器人或代码审查 Demo，而是一个 Agent 应用工程化实践项目，重点关注：

- 多 Agent 协作与职责拆分
- LangGraph 图编排和可视化 Workflow
- Harness Runtime 任务治理
- RAG 知识库生命周期和权限控制
- Skill 插件契约、审批和沙箱执行
- MCP 工具发现、审批、调用和日志
- 人工审核、checkpoint、暂停和恢复
- LLM、RAG、Workflow、MCP 和协作 Benchmark

## 核心能力

### 多 Agent 协作

项目包含多个职责明确的 Agent：

- Planner：拆分目标并生成执行计划
- Project Analyzer：分析项目结构、技术栈和关键模块
- Code Reviewer：执行代码审查并输出风险和建议
- RAG Processor：处理项目文档、切片和知识加工
- Supervisor：汇总结果并进行治理判断
- Human Review：在高风险节点暂停并等待人工决策
- Reporter：生成最终项目报告
- Learning Coach：提供项目学习计划和递进式追问

### 项目分析和代码审查

支持：

- 项目目录扫描
- 技术栈识别
- 关键文件发现
- 模块和架构分析
- 代码风险识别
- 审查建议生成
- Markdown 报告输出

### 治理化 RAG

相较于简单的“切片、向量化、检索、生成” Demo，项目支持：

- 文档 Hash 去重
- 增量入库
- 文档版本管理
- 当前版本控制
- ACL 文档访问控制
- 关键词和语义检索
- 可选 Rerank
- Gold Set 评测
- 项目记忆和手动知识笔记

默认使用 SQLite 作为本地存储，也可以按配置切换到 PgVector。

### Skill 插件体系

Skill 是项目中的可复用任务能力，包含：

- Skill 注册
- 输入输出契约
- 权限声明
- Agent 审批
- 依赖管理
- 版本管理
- 测试执行
- 执行日志
- 失败处理
- Python 子进程或 Docker 沙箱执行

### MCP 工具接入

项目提供两种 MCP Provider：

- Local Provider：本地文件系统和 Git 工具适配，默认可用
- Real Provider：通过 stdio JSON-RPC 接入真实 MCP Server

真实 MCP 模式支持：

- Server 配置保存
- Server 启用和禁用
- `tools/list` 工具发现
- 工具启用和禁用
- Agent 级工具审批
- `tools/call` 调用
- MCP 调用日志

默认配置为本地模式，不会自动连接外部 MCP Server。

### Harness Runtime

Harness Runtime 负责管理 Agent 任务的生命周期：

- 创建任务上下文
- 记录任务状态
- 记录事件时间线
- 保存执行产物
- 创建 checkpoint
- 触发人工审核
- 从 checkpoint 恢复任务
- 处理失败和重试
- 支持历史回放

## 技术栈

### 后端

- Python 3.11+
- FastAPI
- Uvicorn
- LangGraph
- LangChain Core
- Pydantic 2
- Pydantic Settings
- SQLite
- 可选 PgVector

### 前端

- React
- TypeScript
- Vite
- `lucide-react`

### 工程能力

- MCP stdio JSON-RPC
- RAG 混合检索
- LLM Provider 抽象
- Skill Sandbox
- Docker
- Pytest
- Ruff

## 目录结构

```text
Jaycode/
├── app/
│   ├── agents/          # Agent 工具和项目分析能力
│   ├── api/             # FastAPI 路由
│   ├── core/            # 配置
│   ├── graphs/          # LangGraph 协作图和 Workflow 编译
│   ├── harness/         # 任务运行时、事件、策略和上下文
│   ├── marketplace/     # Skill/MCP/Workflow 市场能力
│   ├── persistence/     # SQLite、RAG 和长期记忆存储
│   ├── providers/       # LLM 和 MCP Provider
│   ├── schemas/         # Pydantic 请求和响应模型
│   └── skills/          # Skill 注册、契约、执行和沙箱
├── docs/                # 启动、架构和学习文档
├── examples/            # API 请求示例
├── prompts/             # 系统提示词
├── scripts/             # MCP Server 示例和启动脚本
├── tests/               # 自动化测试
├── web/                 # React/TypeScript 前端
├── .env.example         # 环境变量模板
├── pyproject.toml       # Python 项目和依赖配置
└── README.md
```

## 环境要求

- Python 3.11 或更高版本
- Node.js 18 或更高版本
- npm
- Windows、macOS 或 Linux
- Docker 可选，用于 Docker Skill Sandbox 或 PgVector

## 快速启动

### 1. 创建并激活虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装后端依赖

```powershell
python -m pip install -e ".[dev]"
```

如果需要接入 OpenAI 兼容的 LLM：

```powershell
python -m pip install -e ".[dev,llm]"
```

如果需要 PgVector：

```powershell
python -m pip install -e ".[dev,vector]"
```

### 3. 配置环境变量

复制配置模板：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，填写本地使用的 LLM 配置：

```env
OPENAI_API_KEY=<your-api-key>
OPENAI_BASE_URL=<your-openai-compatible-base-url>
JAYCODE_AGENT_LLM=<your-model-name>
```

不要将真实 `.env` 提交到 Git。

本地开发如需保持免认证模式，必须在 `.env` 中显式设置 `JAYCODE_AUTH_ENABLED=false`；生产环境保持认证开启，并配置 `JAYCODE_API_KEYS`，格式为 `key:role`，角色可选 `user`、`reviewer`、`admin`。Marketplace 远程包默认关闭，MCP stdio command 也必须配置在 `JAYCODE_MCP_ALLOWED_COMMANDS` 白名单中。

### 4. 启动后端

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
```

后端地址：

```text
http://127.0.0.1:8100
```

健康检查：

```text
http://127.0.0.1:8100/health
```

API 文档：

```text
http://127.0.0.1:8100/docs
```

### 5. 启动前端

```powershell
Set-Location web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

前端地址：

```text
http://127.0.0.1:5173
```

### 6. 一键启动

项目提供 Windows 启动脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-start.ps1
```

也可以分别启动：

```powershell
.\start-all.cmd
```

## 常用 API

项目 API 前缀为：

```text
/api/v1
```

常用接口包括：

| 接口 | 作用 |
|---|---|
| `GET /health` | 健康检查 |
| `POST /api/v1/projects/analyze` | 分析项目 |
| `POST /api/v1/code/review` | 代码审查 |
| `POST /api/v1/rag/process` | RAG 文档处理 |
| `POST /api/v1/rag/ingest` | 知识入库 |
| `POST /api/v1/rag/query` | 知识检索 |
| `POST /api/v1/tasks/run` | 创建任务 |
| `POST /api/v1/workflows/run` | 执行 Workflow |
| `POST /api/v1/mcp/servers` | 保存 MCP Server |
| `POST /api/v1/mcp/servers/{server_id}/discover` | 发现 MCP 工具 |
| `POST /api/v1/mcp/tools/call` | 调用 MCP 工具 |
| `POST /api/v1/benchmarks/mcp/run` | 执行 MCP Benchmark |

## MCP 配置

默认使用本地 Provider：

```env
JAYCODE_MCP_PROVIDER=local
```

本地模式直接使用项目内的文件系统和 Git 适配器，不依赖外部 MCP Server。

如果要使用真实 stdio MCP Server：

```env
JAYCODE_MCP_PROVIDER=mcp
```

然后通过 MCP 管理接口保存 Server 配置，执行工具发现，给 Agent 配置审批，最后调用工具。

项目自带的 MCP 示例脚本位于：

```text
scripts/fake_mcp_server.py
scripts/launch_mcp_filesystem.py
scripts/launch_mcp_memory.py
```

## 测试和代码质量

运行测试：

```powershell
python -m pytest
```

运行 Ruff：

```powershell
ruff check .
```

构建前端：

```powershell
Set-Location web
npm run build
```

## Docker

启动 PgVector 相关服务：

```powershell
docker compose -f docker-compose.pgvector.yml up -d
```

Docker Skill Sandbox 需要 Docker Engine 正常运行。生产环境不建议在 Docker 执行失败时静默降级到不隔离的本地执行模式。

## 安全说明

请不要提交以下内容：

```text
.env
.venv/
data/
.jaycode/
.slash_tmp/
%TEMP%/
web/node_modules/
web/dist/
*.db
*.sqlite3
*.log
```

尤其不要把以下内容写入源码或文档：

- OpenAI、DeepSeek 等模型 API Key
- GitHub/GitLab Token
- 数据库密码
- MCP Server 凭证
- 企业内部 API 密钥
- 私钥和证书私密部分

## 学习文档

项目的详细说明位于 `docs/`，包括：

- FastAPI 与项目入口
- Jaycode 架构
- Harness Runtime
- 治理化 RAG
- Skill 插件体系
- MCP Provider 和外部 MCP 接入
- Benchmark 评测
- 环境变量配置
- 前端编排页面

## 当前项目边界

Jaycode 当前重点展示 Agent 应用工程化骨架和关键治理链路。以下能力还可以继续增强：

- 分布式任务队列和多实例调度
- 生产级多租户隔离
- 更完整的远程 MCP Transport
- 更强的外部工具认证和连接池
- 更完善的 Prompt、RAG 和协作评测数据集
- 更严格的生产沙箱和资源配额

## License

本项目遵循仓库中的 `LICENSE` 文件。
