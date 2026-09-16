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

`app.persistence.postgres_store.PostgresTaskStore.init_full_schema()` 目前只提供部分 PostgreSQL 表结构及适配方法，**不等同于全域 Store 接入或完整 CRUD/事务契约**。RAG 表结构由 `PgVectorRagStore` 独立维护；应用在 PostgreSQL 模式仍 fail-closed。应用仍默认使用 SQLite；切换前必须完成 [P1 PostgreSQL 全域接入与迁移收口计划](P1%20PostgreSQL全域接入与迁移收口计划.md) 中所有切换前门禁，不得仅凭配置启用：

```env
JAYCODE_PERSISTENCE_STORE=postgres
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>
```

`JAYCODE_PERSISTENCE_STORE=postgres` 当前会因所有业务域尚未接入而 fail closed，不会静默回退 SQLite。`python -m app.persistence.migrate --check` 只做连接/配置检查；`--export-sqlite` 导出 SQLite 用户表快照；当前 `--verify` 不是源/目标记录集核验，`--import-postgres` 尚未实现。不得将这些命令描述为已具备全量迁移能力。正式迁移前须实现并通过新收口计划中的隔离演练。

PostgreSQL 集成测试只能显式使用 `JAYCODE_TEST_DATABASE_URL`，并连接 loopback 上名称以 `jaycode_test_` 开头的隔离库；禁止将应用 `DATABASE_URL` 直接用于契约测试。未设置隔离测试 URL 时测试应跳过，而非连接应用库。

## P1 阶段 0 安全测试基线

在 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_isolated_baseline.ps1
```

脚本执行 `ruff check app tests` 和全量 pytest。pytest 的默认 SQLite Store 会指向每轮新建的临时文件；进程退出后，脚本校验本轮 owner 标记并只清理本轮临时目录。该脚本清空子进程中的 PG 连接配置并移除专用 PG 测试 URL，不修改 `.env`。报告以不覆盖方式写入 `docs/reports/p1-stage0-baseline-<时间>.md`。

对当前 SQLite 库生成只读结构清单（仅表、列、主外键、`user_version` 和逐表计数，不包含记录内容）：

```powershell
.\.venv\Scripts\python.exe scripts/sqlite_schema_report.py `
  --database data/dev_agent_studio.db `
  --output docs/reports/sqlite-schema-baseline-<日期>.json
```

需要运行真实 PostgreSQL 合约时，须在进程环境中显式设置 `JAYCODE_TEST_ADMIN_URL`，连接 loopback 上名为 `postgres` 的维护数据库；不要使用应用 `DATABASE_URL`。然后运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_postgres_contracts.py
```

runner 自行生成 `jaycode_test_<随机值>` 数据库，在测试进程结束后只删除本轮成功创建的该库；如果创建状态不确定或清理失败，会报错保留，不会尝试清理其他库。未配置 admin URL 时不会连接数据库并明确失败；普通 pytest 下 PG 测试会 skip，skip 不计为通过。

2026-09-15 阶段 0 基线已运行：标准 Python 3.13.15 项目虚拟环境可用；Ruff 通过；SQLite 全量测试 `50 passed, 9 skipped`。本机本轮未检测到 PostgreSQL 服务/客户端且未设置专用 admin URL，因此 PG 集成仍是 skip，不能视为 PostgreSQL 已验证。当前 SQLite 只读结构报告与脱敏测试报告见 `docs/reports/`。

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
