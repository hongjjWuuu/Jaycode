# Jaycode 启动方式

> 当前运行架构（2026-09-17）：API、Worker、Memory、RAG 与业务 Store 均连接 PostgreSQL `jayagent_studio`；pgvector 与主业务库使用同一连接目标。`data/dev_agent_studio.db` 仅保留为迁移前历史库和恢复依据，**不是**当前服务的写入目标。

## 日常启动

不需要让 API 或 Worker 永久在线；需要使用 Web/API 时启动 API，需要处理队列任务时启动 Worker。PostgreSQL 容器必须在二者之前可用。

### 1. 启动 PostgreSQL / pgvector

启动 Docker Desktop 后，在项目根目录运行：

```powershell
cd D:\JayAgent\Jaycode
docker compose -f docker-compose.pgvector.yml up -d
docker compose -f docker-compose.pgvector.yml ps
```

确认 `pgvector` 服务为运行/健康状态。Docker 容器显示的旧名称 `dev-agent-studio-pgvector` 只是容器标识，不影响实际数据库 `jayagent_studio`。

### 2. 启动 API

打开终端 A：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

API 启动会读取 `.env` 中已配置的 PostgreSQL 连接；连接、Schema 或 pgvector 不可用时会明确启动失败，不会写回 SQLite。

### 3. 启动 Worker

需要执行队列任务时，另开终端 B：

```powershell
cd D:\JayAgent\Jaycode
.\.venv\Scripts\python.exe -m app.harness.worker --worker-id local-worker
```

Worker 正常轮询时通常没有持续输出。Worker 未运行不会丢任务，但新任务会保持 `queued`，直到有 Worker 领取。

### 4. 验证并访问

在第三个 PowerShell 窗口运行：

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
Invoke-RestMethod http://127.0.0.1:8100/ready
```

两者应分别返回 `status: ok` 与 `status: ready`。然后访问：

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

## 停止与恢复原则

- 停止 API 或 Worker：在各自终端按 `Ctrl+C`。
- PostgreSQL 容器可继续运行；下次启动会继续使用 `jayagent_studio`，**无需再次迁移**。
- 若需要停止容器：`docker compose -f docker-compose.pgvector.yml stop`。不要运行会删除卷的命令。
- PostgreSQL 已是权威库。发生故障时不要只修改 `.env` 切回 SQLite；应先冻结写入、保留现状并执行数据对账与恢复方案。

## 可选：由 API 进程守护 Worker

若希望只启动 API 即由其创建并守护 Worker，可在维护后审慎设置 `.env`：

```env
JAYCODE_WORKER_SUPERVISOR_ENABLED=true
JAYCODE_WORKER_COUNT=1
```

重启 API 后生效。未启用时，采用上文的独立 Worker 启动方式，便于本机观察和排障。
