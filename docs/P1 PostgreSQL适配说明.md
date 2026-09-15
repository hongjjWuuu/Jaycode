# Jaycode P1 PostgreSQL 适配说明

当前默认数据库仍为 SQLite，适用于本地开发和低并发场景。PostgreSQL 适配本轮以 RAG/pgvector Store 为基础，不自动迁移或覆盖现有 SQLite 数据。

## 配置

```env
JAYCODE_RAG_STORE=pgvector
PGVECTOR_DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>
JAYCODE_EMBEDDING_DIM=1536
```

未配置连接串时，PostgreSQL 集成测试必须跳过，不得将 SQLite 结果冒充 PostgreSQL 验证结果。

## 验证和回滚

1. 在独立 PostgreSQL 数据库执行应用启动和 RAG schema 初始化。
2. 执行 RAG 文档、分块、ACL、Gold Set 和向量查询契约测试。
3. 验证事务失败后不会产生半提交记录。
4. 回滚时将 `JAYCODE_RAG_STORE=sqlite`，保留 PostgreSQL 数据库，不删除 SQLite 历史数据。

## 全域 Store 与显式切换

`app.persistence.postgres_store.PostgresTaskStore.init_full_schema()` 提供 Task、Event、Artifact、Workflow、Review、Skill、MCP、Marketplace、Audit、Memory、LLM、Benchmark 和 RAG 的幂等 PostgreSQL schema 契约。应用仍默认使用 SQLite；切换前必须显式设置：

```env
JAYCODE_PERSISTENCE_STORE=postgres
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>
```

`JAYCODE_PERSISTENCE_STORE=postgres` 且连接串缺失或连接失败时会 fail closed，不会静默回退 SQLite。`python -m app.persistence.migrate --check` 只做连接/配置检查；`--export-sqlite` 生成只读 JSON 快照，`--verify` 只验证当前配置，不会自动迁移或删除历史数据。导入仍需人工审核后执行。

## Worker 与监控

生产环境显式设置 `JAYCODE_WORKER_SUPERVISOR_ENABLED=true` 后，应用会启动本机 Worker Supervisor；开发环境保持关闭，使用 `python -m app.harness.worker` 手工验证即可。

监控端点为 `/metrics`（Prometheus 文本格式）和 `/ready`（数据库/Worker 就绪状态）。

启用 `JAYCODE_WORKER_SUPERVISOR_ENABLED=true` 后，Supervisor 会启动并守护本地 Worker；连续异常退出达到 `JAYCODE_WORKER_SUPERVISOR_MAX_RESTARTS` 后进入 `degraded`，`/ready` 返回非就绪。

Windows 本机可选用 `scripts/windows/jaycode-task.ps1` 注册用户登录启动项：

```powershell
.\scripts\windows\jaycode-task.ps1 -Action install
.\scripts\windows\jaycode-task.ps1 -Action status
```

该脚本不会被应用自动执行；执行 `install` 前需在 `.env` 中显式启用 Supervisor。当前任务计划程序以用户登录为触发条件，确保访问项目用户目录与数据库权限。
