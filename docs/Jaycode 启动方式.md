# Jaycode 启动方式

> 当前运行架构（2026-09-17）：API、Worker、Memory、RAG 与业务 Store 均连接 PostgreSQL `jayagent_studio`；pgvector 与主业务库使用同一连接目标。`data/dev_agent_studio.db` 仅保留为迁移前历史库和恢复依据，**不是**当前服务的写入目标。

## 运行模式与前提

日常使用不要求 API 或 Worker 24 小时运行，但 PostgreSQL 必须先于二者可用。Worker 有两种**互斥**模式：独立 Worker，或由 API Supervisor 创建的 Worker；不要同时启用。

首次启动或 Python 环境异常时，在项目根目录先检查：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
.\.venv\Scripts\python.exe -m ruff --version
```

若任一命令不能运行，先修复环境，勿用未安装依赖的系统 Python 替代项目环境：

```powershell
Rename-Item .venv .venv-backup
C:\Users\JayWuuu\AppData\Local\Programs\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,vector]"
```

确认可用后再删除 `.venv-backup`；此操作不修改 PostgreSQL、`.env` 或业务数据。

私有 `.env` 必须使以下两条连接指向同一 PostgreSQL 目标，且不得提交真实密码或 Token：

```env
JAYCODE_PERSISTENCE_STORE=postgres
JAYCODE_RAG_STORE=pgvector
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
PGVECTOR_DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
```

生产环境还必须保持 `JAYCODE_AUTH_ENABLED=true` 并配置 `JAYCODE_API_KEYS`；调用 API 时使用 `Authorization: Bearer <key>`。本地开发可显式设为 `false`。

## 日常启动

### 1. 启动 PostgreSQL / pgvector

启动 Docker Desktop 后，在项目根目录运行：

```powershell
cd D:\JayAgent\Jaycode
docker compose -f docker-compose.pgvector.yml up -d
docker compose -f docker-compose.pgvector.yml ps
```

确认 `pgvector` 服务为运行/健康状态。Docker 容器显示的旧名称 `dev-agent-studio-pgvector` 只是容器标识，不影响实际数据库 `jayagent_studio`。

### 2. 构建前端（首次、前端更新或 `web/dist` 不存在时）

FastAPI 只在 `web/dist` 存在时托管正式页面：

```powershell
cd D:\JayAgent\Jaycode\web
npm ci
npm run build
```

### 3. 启动 API

打开终端 A：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

API 启动会读取 `.env` 中已配置的 PostgreSQL 连接；连接、Schema 或 pgvector 不可用时会明确启动失败，不会写回 SQLite。

### 4. 选择一种 Worker 模式

**默认：独立 Worker。** 需要执行队列任务时，另开终端 B：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m app.harness.worker --worker-id local-worker
```

Worker 正常轮询时通常没有持续输出。Worker 未运行不会丢任务，但新任务会保持 `queued`，直到有 Worker 领取。

**可选：API Supervisor。** 仅在需要 API 自动守护 Worker 时，在私有 `.env` 设置下列值并重启 API；此模式下不要再启动独立 Worker：

```env
JAYCODE_WORKER_SUPERVISOR_ENABLED=true
JAYCODE_WORKER_COUNT=1
JAYCODE_WORKER_SUPERVISOR_MAX_RESTARTS=5
JAYCODE_WORKER_SUPERVISOR_STARTUP_TIMEOUT_SECONDS=5
```

### 5. 验证并访问

在第三个 PowerShell 窗口运行：

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
Invoke-RestMethod http://127.0.0.1:8100/ready
```

- `/health` 返回 `status: ok`：API 进程存活。
- `/ready` 返回 `status: ready`：PostgreSQL 可用；**只有启用 Supervisor 时**还会检查受管 Worker。
- 独立 Worker 不由 `/ready` 判定；通过工作台“运营”页、Worker 注册状态或提交测试任务确认其领取任务。

然后访问：

```text
http://127.0.0.1:8100/
```

API 文档位于 `http://127.0.0.1:8100/docs`。

## 前端开发模式

后端仍按上面的 API 步骤启动；需要热更新 React 页面时再开启 Vite：

```powershell
cd D:\JayAgent\Jaycode\web
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 `http://127.0.0.1:5173/`。正常使用已构建的前端时不需要启动 Vite，FastAPI 会托管 `web/dist`。

## 常见排障

```powershell
docker compose -f docker-compose.pgvector.yml ps
docker compose -f docker-compose.pgvector.yml logs --tail 100 pgvector
Get-NetTCPConnection -LocalPort 8100 -ErrorAction SilentlyContinue
```

- PostgreSQL 未就绪：确认 Docker Desktop 已启动，检查 `pgvector` 日志；不要删除 Docker 卷。
- 8100 已占用：停止旧 API 进程后再启动，不要同时运行多个 API 实例。
- API 启动失败：核对 `.env` 中两个 PostgreSQL URL 指向同一 `jayagent_studio`，再检查虚拟环境自检命令。
- Worker 未领取任务：确认只启用一种 Worker 模式，在运营页查看 Worker 与队列状态。

## 停止、备份与恢复原则

- 停止 API 或 Worker：在各自终端按 `Ctrl+C`。
- PostgreSQL 容器可继续运行；下次启动会继续使用 `jayagent_studio`，**无需再次迁移**。
- 若需要停止容器：`docker compose -f docker-compose.pgvector.yml stop`。不要运行会删除卷的命令。
- PostgreSQL 已是权威库。发生故障时不要只修改 `.env` 切回 SQLite；应先冻结写入、保留现状并执行数据对账与恢复方案。
- 每日备份、Task Scheduler 与隔离恢复演练见 [P3 单机运维手册](P3%20单机运维手册.md)。
- API 自动启动的 Windows 计划任务与每日备份任务是两项独立配置，均需操作者显式注册；不要在未确认 Supervisor 配置前注册 API 自动启动任务。
