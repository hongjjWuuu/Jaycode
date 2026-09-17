
这份配置可以分成 6 组：

1. 基础应用配置
2. LLM 配置
3. RAG / Memory 配置
4. MCP 配置
5. Skill Sandbox 配置
6. 可选的评测 / 价格 / 向量数据库配置

---

> **当前运行状态（2026-09-17）**：以下部分 SQLite 示例保留为早期学习材料，不是当前 Jaycode 的生效配置。正式运行使用 PostgreSQL `jayagent_studio`；`.env` 中 `JAYCODE_PERSISTENCE_STORE=postgres`、`JAYCODE_RAG_STORE=pgvector`，且 `DATABASE_URL` 与 `PGVECTOR_DATABASE_URL` 必须指向同一数据库。不要在文档中填写真实密码或 Token，也不要为了“简化启动”把它们改回 SQLite。

## 当前最小运行配置

```env
JAYCODE_PERSISTENCE_STORE=postgres
JAYCODE_RAG_STORE=pgvector
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
PGVECTOR_DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
JAYCODE_MEMORY_EXTRACTOR=rule
JAYCODE_MCP_PROVIDER=local
JAYCODE_SKILL_SANDBOX=subprocess
```

日常启动还需要 Docker PostgreSQL、API 与需要时的 Worker；完整步骤见 [Jaycode 启动方式](../Jaycode%20启动方式.md)。

---

## 1. 基础应用配置

```
APP_NAME=Jaycode
APP_ENV=dev
MAX_SCAN_FILES=800
MAX_FILE_PREVIEW_CHARS=4000
```

作用：

- `APP_NAME`
    - 应用显示名称
    - 影响后端 `/health`、页面标题、部分日志和展示文案
- `APP_ENV`
    - 环境标识
    - 一般是 `dev`、`test`、`prod`
- `MAX_SCAN_FILES`
    - 项目扫描最多读取多少个文件
    - 太大可能慢，太小会漏分析
- `MAX_FILE_PREVIEW_CHARS`
    - 单个文件预览最大字符数
    - 避免一次读太多内容

---

## 2. LLM 配置

### 2.1 主模型

```
OPENAI_API_KEY= sk-...
OPENAI_BASE_URL=https://api.deepseek.com
JAYCODE_AGENT_LLM=deepseek-v4-flash
```

作用：

- `OPENAI_API_KEY`
    - 你的模型调用密钥
    - 你要求用 `sk-XXX` 代替时，说明这里应该放真实 key 或占位 key
- `OPENAI_BASE_URL`
    - OpenAI 兼容接口地址
    - 你现在用的是 DeepSeek 的兼容地址
- `JAYCODE_AGENT_LLM`
    - 默认给所有 Agent 用的模型名

### 重要提醒

你这份里 `OPENAI_API_KEY` 前面有一个空格：

```
OPENAI_API_KEY= sk-...
```

建议改成：

```
OPENAI_API_KEY=sk-XXX
```

或者真实 key 时：

```
OPENAI_API_KEY=你的真实key
```

这个前导空格最好去掉，避免某些读取逻辑把它当成值的一部分。

---

### 2.2 单独 Agent 模型覆盖

```
JAYCODE_AGENT_LLM_PLANNER=deepseek-v4-flash
JAYCODE_AGENT_LLM_REPORTER=deepseek-v4-flash
JAYCODE_AGENT_LLM_SUPERVISOR=deepseek-v4-flash
JAYCODE_AGENT_LLM_PROJECT_ANALYZER=deepseek-v4-flash
JAYCODE_AGENT_LLM_CODE_REVIEWER=deepseek-v4-flash
JAYCODE_AGENT_LLM_FILE_REVIEWER=deepseek-v4-flash
JAYCODE_AGENT_LLM_TASK_QA=deepseek-v4-flash
JAYCODE_AGENT_LLM_LEARNING_COACH=deepseek-v4-flash
JAYCODE_AGENT_LLM_MEMORY_EXTRACTOR=deepseek-v4-flash
JAYCODE_AGENT_LLM_AGENT_MODELS=planner:deepseek-v4-flash,reporter:deepseek-v4-flash,supervisor:deepseek-v4-flash
```

作用：

- 这些是给不同 Agent 单独指定模型
- 如果不写，系统通常会回退到 `JAYCODE_AGENT_LLM`
- 适合：
    - planner 用便宜模型
    - reporter 用更强模型
    - supervisor 用更稳模型

如果你想先简化启动，可以先只保留：

```
JAYCODE_AGENT_LLM=deepseek-v4-flash
```

这些覆盖项都可以先不写。

---

### 2.3 Prompt 版本覆盖

```
JAYCODE_PROMPT_PLANNER=planner.v2
JAYCODE_PROMPT_REPORTER=reporter.v2
JAYCODE_PROMPT_SUPERVISOR=supervisor.v2
JAYCODE_PROMPT_PROJECT_ANALYZER_ARCHITECTURE=project_analyzer.architecture.v2
JAYCODE_PROMPT_CODE_REVIEWER_SUGGESTIONS=code_reviewer.suggestions.v2
JAYCODE_PROMPT_FILE_REVIEWER_SEMANTIC=file_reviewer.semantic.v2
JAYCODE_PROMPT_TASK_QA=task_qa.v2
JAYCODE_PROMPT_LEARNING_COACH_REPLY=learning_coach.reply.v2
JAYCODE_PROMPT_LEARNING_COACH_QUESTIONS=learning_coach.questions.v2
JAYCODE_PROMPT_MEMORY_EXTRACTOR=memory_extractor.v1
```

作用：

- 控制不同 Agent 使用哪个 prompt 版本
- 这属于“可治理资产”
- 适合你后面做 Prompt A/B Test、调优和回滚

最小启动时不是必须。

---

## 3. Memory 配置

```
JAYCODE_MEMORY_EXTRACTOR=rule
```

作用：

- 控制长期记忆抽取方式
- `rule` 表示用规则，不依赖 LLM
- `llm` 表示用模型抽取更智能的长期记忆候选

### 现在这个值的意义

- `rule` 最稳，适合先启动
- 如果你要记忆自动化更强，可以改成：
    
    ```
    JAYCODE_MEMORY_EXTRACTOR=llm
    ```
    
    但前提是 `OPENAI_API_KEY` 必须真实可用

---

## 4. LLM 价格估算

```
JAYCODE_LLM_PRICE_GPT_4O_MINI_INPUT_PER_1M=
JAYCODE_LLM_PRICE_GPT_4O_MINI_OUTPUT_PER_1M=
```

作用：

- 给 dashboard 算 token 成本用
- 不影响核心启动
- 可以留空

---

## 5. RAG 配置（历史 SQLite 示例）

你现在这部分是：

```
JAYCODE_RAG_STORE=sqlite
JAYCODE_RAG_RERANKER=off
PGVECTOR_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/jaycode
DATABASE_URL=
JAYCODE_EMBEDDING_MODEL=text-embedding-3-small
JAYCODE_EMBEDDING_DIM=1536
```

### 5.1 `JAYCODE_RAG_STORE=sqlite`

意思是：

- 当前 RAG 后端用 SQLite
- 这是最简单、最稳的模式

### 5.2 `JAYCODE_RAG_RERANKER=off`

意思是：

- 关闭 reranker
- 检索只用基础排序
- 最稳

### 5.3 `PGVECTOR_DATABASE_URL=...`

这个是给 **PgVector** 模式准备的。

但你当前 `JAYCODE_RAG_STORE=sqlite`，所以：

- 这个值现在 **不会生效**
- 只是预先放着，等你切换到 pgvector 再用

如果你现在只是想先稳定启动，完全可以把它留空：

```
PGVECTOR_DATABASE_URL=
```

### 5.4 `DATABASE_URL=`

也是数据库连接备用项，当前为空没问题。

### 5.5 `JAYCODE_EMBEDDING_MODEL` 和 `JAYCODE_EMBEDDING_DIM`

作用：

- 向量 embedding 模型名称
- 向量维度

你当前配置是标准默认值，可以保留。

---

## 6. MCP 配置

```
JAYCODE_MCP_PROVIDER=local
```

作用：

- `local`：用本地工具适配器
- `mcp`：走真实 MCP Server

### 当前推荐

- 先用 `local`
- 因为它最容易启动，不依赖外部 MCP server

如果你切成：

```
JAYCODE_MCP_PROVIDER=mcp
```

那还得再配 MCP Server，不然会报错。

---

## 7. Skill Sandbox 配置

```
JAYCODE_SKILL_SANDBOX=subprocess
JAYCODE_SKILL_SANDBOX_IMAGE=python:3.13-slim
JAYCODE_SKILL_SANDBOX_MEMORY=256m
JAYCODE_SKILL_SANDBOX_CPUS=0.5
JAYCODE_SKILL_SANDBOX_PIDS_LIMIT=64
JAYCODE_SKILL_SANDBOX_FALLBACK=false
```

作用：

- `subprocess`
    - 本地子进程沙箱
    - 最容易启动
- `docker`
    - 更强隔离
    - 但需要 Docker
- `FALLBACK=false`
    - Docker 失败时不自动降级

### 当前推荐

先保持：

```
JAYCODE_SKILL_SANDBOX=subprocess
```

这是最稳的。

---

# 历史 `.env` 示例的说明

## 1. `OPENAI_API_KEY` 前面的空格

现在建议改成：

```
OPENAI_API_KEY=sk-XXX
```

不要写成：

```
OPENAI_API_KEY= sk-XXX
```

## 2. `PGVECTOR_DATABASE_URL`

如果你当前不是用 pgvector，可以先空着：

```
PGVECTOR_DATABASE_URL=
```

因为你现在是：

```
JAYCODE_RAG_STORE=sqlite
```

两者不冲突，但这个值暂时不会被用到。

## 3. `JAYCODE_AGENT_LLM_*` 和 `JAYCODE_PROMPT_*`

这些是完整功能配置，不影响启动，但如果你想先简化，可以先删掉，只保留最核心几项。

---

# 历史 SQLite 最小启动示例

你最少只需要保留：

```
APP_NAME=Jaycode
APP_ENV=dev
OPENAI_API_KEY=sk-XXX
OPENAI_BASE_URL=https://api.deepseek.com
JAYCODE_AGENT_LLM=deepseek-v4-flash
JAYCODE_MEMORY_EXTRACTOR=rule
JAYCODE_RAG_STORE=sqlite
JAYCODE_RAG_RERANKER=off
JAYCODE_MCP_PROVIDER=local
JAYCODE_SKILL_SANDBOX=subprocess
JAYCODE_SKILL_SANDBOX_FALLBACK=false
```

---

# 历史 SQLite 完整功能示例

那就是你现在这份，外加这几个建议：

- 去掉 `OPENAI_API_KEY` 前导空格
- `PGVECTOR_DATABASE_URL` 如果暂时不用就清空
- 保留 `JAYCODE_AGENT_LLM_*`
- 保留 `JAYCODE_PROMPT_*`
- 保留 `JAYCODE_LLM_PRICE_*`
