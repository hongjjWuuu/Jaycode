# Jaycode 启动方式

> 正式运行使用 PostgreSQL `jayagent_studio`（含 pgvector）。`data/dev_agent_studio.db` 仅是迁移历史和兼容依据，不能作为日常服务的写入目标。

## 启动：只做这三步

日常使用不需要重新迁移数据库、重建 Python 环境或重新安装前端依赖。API 和 Worker 也不必 24 小时运行；需要使用工作台时再启动即可。

### 1. 确认 PostgreSQL 已运行

先打开 Docker Desktop。在 PowerShell 中检查是否已有容器占用 PostgreSQL 端口：

```powershell
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
```

若输出中已有一个 PostgreSQL 容器使用 `5432`（例如 `jaycode-postgres` 或 `dev-agent-studio-pgvector`），它就是当前数据库，直接进入下一步。

若没有运行中的 PostgreSQL 容器，启动项目配置的容器：

```powershell
cd D:\JayAgent\Jaycode
docker compose -f docker-compose.pgvector.yml up -d
docker compose -f docker-compose.pgvector.yml ps
```

若出现 `port is already allocated`，表示已有容器正在占用 `5432`；**不要再创建第二个数据库容器，也不要删除 Docker 卷**。回到上面的 `docker ps` 找到已有容器后继续使用它。

### 2. 启动 API

打开终端 A：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

看到下面一行即表示 API 已启动：

```text
Uvicorn running on http://127.0.0.1:8100
```

### 3. 启动一个 Worker

需要执行分析、审查等排队任务时，打开终端 B：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m app.harness.worker --worker-id local-worker
```

Worker 正常轮询时通常没有持续输出。未启动 Worker 不会丢任务，但任务会停留在 `queued`，直到 Worker 领取。

然后访问工作台：<http://127.0.0.1:8100/>。

停止 API 或 Worker 时，在各自终端按 `Ctrl+C`。PostgreSQL 可以继续运行。

## 第一次配置时才需要做

### 配置私有 `.env`

从 `.env.example` 创建私有 `.env`，并确保下面四项存在。两条 URL 必须指向同一个 PostgreSQL `jayagent_studio`；真实密码和 API Key 不得提交到 Git：

```env
JAYCODE_PERSISTENCE_STORE=postgres
JAYCODE_RAG_STORE=pgvector
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
PGVECTOR_DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
```

本地个人开发可设 `JAYCODE_AUTH_ENABLED=false`。若 API 会暴露给其他设备或网络，则设为 `true`，配置 `JAYCODE_API_KEYS`，并在请求中携带 `Authorization: Bearer <key>`。

### 安装或更新前端依赖

仅在首次克隆项目、`web/node_modules` 不存在、或 `package-lock.json` 变更后执行：

```powershell
cd D:\JayAgent\Jaycode\web
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
npm ci
npm run build
```

`npm ci` 只安装当前项目的前端依赖；它不会创建新的 Python `.venv`。日常使用已构建的页面时，不必运行这些命令。

### 选择 API 自动守护 Worker（可选）

上面的独立 Worker 是默认且最容易排查的模式。若你希望启动 API 时自动拉起 Worker，才在 `.env` 设置：

```env
JAYCODE_WORKER_SUPERVISOR_ENABLED=true
JAYCODE_WORKER_COUNT=1
JAYCODE_WORKER_SUPERVISOR_MAX_RESTARTS=5
JAYCODE_WORKER_SUPERVISOR_STARTUP_TIMEOUT_SECONDS=5
```

重启 API 后生效。启用 Supervisor 时，**不要再手动启动独立 Worker**；不要同时使用两种 Worker 模式。

## 验证是否正常

另开一个 PowerShell 窗口：

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
Invoke-RestMethod http://127.0.0.1:8100/ready
```

- `/health` 返回 `status: ok`：API 进程存活。
- `/ready` 返回 `status: ready`：PostgreSQL 可用；使用 Supervisor 时也会检查受管 Worker。
- 独立 Worker 的状态请在工作台“运营”页查看，或提交一个测试任务确认它被领取。

## 只在开发前端时使用 Vite

修改 React 页面并希望热更新时，在 API 继续运行的前提下另开终端：

```powershell
cd D:\JayAgent\Jaycode\web
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 <http://127.0.0.1:5173/>。正常使用时不需要 Vite，API 会托管已构建的 `web/dist`。

## 出现问题再看这里

### `No module named uvicorn`

现有 `.venv` 缺少项目运行依赖。无需新建虚拟环境，直接补全：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m pip install -e ".[dev,vector]"
.\.venv\Scripts\python.exe -m uvicorn --version
```

### `npm.ps1` 被 PowerShell 阻止

仅对当前终端临时放行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

或使用 `npm.cmd ci`，无需修改系统级执行策略。

### Python 环境无法运行

先检查：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
.\.venv\Scripts\python.exe -m ruff --version
```

只有当前 `.venv` 已损坏且上述修复无效时，才重建。先保留旧环境作为回退：

```powershell
Rename-Item .venv .venv-backup
C:\Users\JayWuuu\AppData\Local\Programs\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,vector]"
```

确认 API、Worker 和测试均正常后，再删除 `.venv-backup`。此操作不会修改 PostgreSQL、`.env` 或业务数据。

### PostgreSQL、API 或 Worker 异常

```powershell
docker compose -f docker-compose.pgvector.yml ps
docker compose -f docker-compose.pgvector.yml logs --tail 100 pgvector
Get-NetTCPConnection -LocalPort 8100 -ErrorAction SilentlyContinue
```

- PostgreSQL 未就绪：确认 Docker Desktop 已启动并查看日志；不要删除 Docker 卷。
- `8100` 已占用：停止旧 API 进程后再启动，不要同时运行多个 API 实例。
- Worker 未领取任务：确认只启用一种 Worker 模式，并在运营页检查 Worker 与队列。
- API 无法连接数据库：检查 `.env` 的两条 PostgreSQL URL 是否指向同一个 `jayagent_studio`。

## 数据安全与运维

- 不要重新执行迁移或切换脚本；PostgreSQL 已是权威库。
- 发生故障时，不要仅修改 `.env` 切回 SQLite；先冻结写入、保留现状，再按恢复方案处理。
- 停止容器使用 `docker compose -f docker-compose.pgvector.yml stop`；不要使用会删除卷的命令。
- 每日备份、Task Scheduler 与隔离恢复演练见 [P3 单机运维手册](P3%20单机运维手册.md)。
