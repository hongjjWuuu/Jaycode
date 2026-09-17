# Jaycode PostgreSQL 运行与运维说明

> 状态（2026-09-17）：P1 PostgreSQL 全域接入、35 表迁移、逐表核验、API/Worker 运行时验证及跨域写入烟测均已完成。`jayagent_studio` 是权威持久化库。

## 运行配置

本机 `.env` 保持以下逻辑；不要将真实连接串、密码或 Token 提交到仓库：

```env
JAYCODE_PERSISTENCE_STORE=postgres
JAYCODE_RAG_STORE=pgvector
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
PGVECTOR_DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/jayagent_studio
JAYCODE_EMBEDDING_DIM=1536
```

主业务库与 pgvector 必须是同一个主机、端口和数据库。连接、Schema、迁移版本或 pgvector 不可用时，应用会 fail-closed，绝不会降级写入 SQLite。

## 日常启动

1. 启动 Docker Desktop 与 PostgreSQL 服务：

   ```powershell
   cd D:\JayAgent\Jaycode
   docker compose -f docker-compose.pgvector.yml up -d
   docker compose -f docker-compose.pgvector.yml ps
   ```

2. 在终端 A 启动 API：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
   ```

3. 需要消费任务时，在终端 B 启动 Worker：

   ```powershell
   .\.venv\Scripts\python.exe -m app.harness.worker --worker-id local-worker
   ```

4. 验证：

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8100/health
   Invoke-RestMethod http://127.0.0.1:8100/ready
   ```

API 与 Worker 不必 24 小时运行；Worker 停止时任务会保持 `queued`，不会丢失。启用 `JAYCODE_WORKER_SUPERVISOR_ENABLED=true` 后，API 可启动并守护本地 Worker。

## 数据状态与恢复原则

- `jayagent_studio`：当前业务、RAG、Memory 与向量数据的权威库。
- `data/dev_agent_studio.db`：迁移前 SQLite 原库，仅保留用于审计和恢复依据。
- `data/backups/dev_agent_studio-pre-postgres-*.db`：不可覆盖的一致性维护备份。
- 旧 PostgreSQL 库和 Docker 卷均保留；Docker 容器名即使仍是 `dev-agent-studio-pgvector`，也不改变实际使用的数据库名。

PostgreSQL 已接受新业务写入，**不得只修改 `.env` 回退到 SQLite**。出现恢复需求时，先冻结 API/Worker 写入，保留当前 PostgreSQL 与 SQLite 数据，完成数据对账后再执行经批准的恢复方案。

## 测试隔离

测试只能使用专用、随机的 loopback 数据库，绝不使用应用的 `DATABASE_URL`：

```powershell
# 当前 PowerShell 中设置不显示在日志的维护连接后运行
.\.venv\Scripts\python.exe scripts/run_postgres_contracts.py
```

运行器会创建并清理本次 `jaycode_test_*` 临时库。常规 SQLite 基线、阶段五门禁和正式切换报告分别位于 `artifacts/quality-gates/` 与 `artifacts/cutover/`。

正式迁移已完成；`scripts/run_stage6_cutover.ps1` 是受控维护工具，不能作为日常启动或重复导入命令。
