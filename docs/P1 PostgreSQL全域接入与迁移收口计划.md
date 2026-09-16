# P1 PostgreSQL 全域接入与迁移收口计划

> 状态：阶段四已通过；阶段五（最终切换前质量门禁）待实施。当前不得切换 PostgreSQL、修改生效 `.env`、导入现有 SQLite 数据或写入现有 PostgreSQL 业务库。

## 目标与当前基线

目标是完成所有业务域 PostgreSQL 持久化、跨后端契约、API/Worker 端到端验证及 SQLite 全量迁移核验，并在全部门禁通过后执行正式切换。

当前可确认的基线：

- `app/persistence/factory.py` 的 `PersistenceStores` 已暴露 12 个领域入口；PostgreSQL 仍只允许在隔离测试数据库中验证，生产配置保持 SQLite。
- `app/persistence/postgres_store.py` 已有部分领域方法和 schema，但尚未证明所有业务调用都通过统一 Store，也没有全域共用契约。
- `app/persistence/rag_store.py` 有独立 SQLite/PgVector 实现；统一工厂和 PostgreSQL 主连接的一致性仍需端到端验证。
- `app/persistence/migrate.py` 可做 SQLite 一致性备份、清单和全表 JSON 导出；`--import-postgres` 未实现，`--verify` 不比较源/目标记录集。
- 新增 PostgreSQL 集成测试须使用 `JAYCODE_TEST_DATABASE_URL`，主机限 loopback 且数据库名必须以 `jaycode_test_` 开头。不得用应用 `DATABASE_URL` 代替。
- 用户普通 PowerShell 已确认标准 Python 3.13.15 与项目 `.venv` 可用；Codex 受限执行环境不能代表本机环境。真实 PostgreSQL 验证必须由隔离测试运行器在用户终端执行。

## 不可突破的安全边界

1. 阶段 0—4 只允许使用可丢弃的测试 SQLite 文件和专用隔离 PostgreSQL 测试库。
2. 不读取、打印或提交连接密码；测试日志、报告不得包含连接串。
3. 不改 `.env`、不迁移当前 `data/dev_agent_studio.db`、不触碰现有 PostgreSQL 业务库、不注册 Windows 计划任务。
4. 迁移映射必须显式；未知表、列、Schema 版本、目标非空冲突一律停止，不忽略、不覆盖、不清库。
5. 只有阶段 0—5 全部通过且用户确认进入切换窗口后，才能执行阶段 6。PostgreSQL 接收新业务写入后，不可仅改配置回退。

## 阶段 0：建立可复现的安全测试基线

### 工作项

- 确认项目专用 Python、pytest、Ruff、psycopg 与前端依赖可用；命令记录解释器绝对路径和版本，但不输出任何密钥。
- 修复测试启动方式，使 PostgreSQL 测试无 `JAYCODE_TEST_DATABASE_URL` 时明确 skip；提供本机隔离数据库的创建、运行、清理说明或脚本。
- 测试启动前验证 URL 是 loopback 且数据库名为 `jaycode_test_*`；在测试结束时只删除本次创建的随机测试库，绝不自动删除调用者已有数据库。
- 在只读/临时数据副本上记录 SQLite schema 版本、业务表清单、字段、主键、外键和每表行数；不复制或展示敏感内容。
- 基线命令：

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m pytest -q tests
```

### 交付物与门禁

- 提交脱敏基线报告，区分 pass / fail / skip / 未执行及失败原因。
- SQLite 基线测试全过；PG 未配置时只可标记 skip，不能计为 PG 通过。
- 隔离数据库 guard 的正反例测试通过。此门禁未过，不运行任何 PG 写测试。

## 阶段 1：盘点接口并定义统一 Store 契约

### 工作项

- 以 `SQLiteTaskStore`、`SQLiteMemoryStore`、`SQLiteRagStore` 的公开方法和真实调用点为基准建立接口清单。
- `PersistenceStores` 至少显式提供 `task`、`workflow`、`review`、`skill`、`mcp`、`marketplace`、`audit`、`memory`、`llm`、`prompt`、`benchmark`、`rag`；可由多个领域共用一个适配器实例，但公开域边界和能力必须明确。
- 为每个方法记录签名、返回值、分页、唯一键、事务范围、异常语义及对应 SQLite 表。
- 将 API、Worker、Supervisor、Benchmark、Skill、MCP、Marketplace、Memory、LLM/RAG 服务中的直连 SQLite 全局对象逐处迁到 Store 注入/工厂。新增检查避免生产业务路径重新导入全局 `task_store` 等单例。
- PostgreSQL 配置必须 fail-closed：缺失任何适配、连接失败、Schema 版本不兼容均启动失败；严禁回退 SQLite。
- PG 主库与 RAG 使用同一 `DATABASE_URL`。若设置 `PGVECTOR_DATABASE_URL`，启动时校验主机、端口、数据库名一致。

### 主要文件范围

`app/persistence/factory.py`、`sqlite_store.py`、`postgres_store.py`、`postgres_memory_store.py`、`rag_store.py`、`postgres_config.py`，以及 `app/api/`、`app/harness/`、`app/skills/`、`app/marketplace/`、`app/providers/`、`app/benchmark_runner.py`。

### 门禁

- 每个公开 SQLite 方法都有对应 PostgreSQL 实现或明确列入未支持清单；未支持项不得允许 PostgreSQL 启动。
- 静态依赖扫描证明 API/Worker 业务路径通过工厂取 Store。
- SQLite 全量测试通过；PostgreSQL 故障和不完整适配测试证明 fail-closed。

### 阶段 1 实施记录（2026-09-16）

- 已新增 `app/persistence/contracts.py`：定义 12 个领域的类型契约、SQLite 表映射、方法清单及 PostgreSQL 支持状态。
- `PersistenceStores` 已显式暴露全部 12 个领域；SQLite 使用同一路径构建 Task、Memory、RAG，并让兼容领域共享 Task 适配器实例。
- API、Worker、Supervisor、Benchmark、Skill、MCP、Marketplace、LLM、Workflow 与安全审计已改为在实际调用时获取 `PersistenceStores` 的对应领域入口；生产模块不得再导入工厂代理或 SQLite 全局单例。
- PgVector/SQLite RAG 均暴露 `source`、`embed_documents`、`embed_query`，维持统一公开契约；这不会改变 SQLite 的现有检索实现。
- 阶段一测试新增 Bundle 完整性、SQLite 方法契约、PostgreSQL 缺配置/不完整矩阵 fail-closed、RAG 接口一致性与 AST 单例导入扫描。真实 PostgreSQL 契约及 CRUD 验证仍属于阶段二、三，尚未完成。
- 2026-09-16 回归结果：`ruff check app tests` 通过；`pytest -q tests` 为 `55 passed, 9 skipped`。9 个跳过项均要求显式隔离 PostgreSQL 测试 URL，未计为 PostgreSQL 验证通过。

## 阶段 2：完成 PostgreSQL schema 与各域 CRUD/事务

### 实施顺序

1. Task、队列、事件、产物、幂等键、租约/心跳。
2. Workflow、Human Review、checkpoint 和审核转换事务。
3. Skill、MCP、Marketplace、Security Audit。
4. Memory 与生命周期事件。
5. LLM Trace、Prompt Version、Benchmark Run/Result。
6. RAG Document、Chunk、ACL、版本、Gold Case 与向量查询。

### 工作项

- schema 采用显式版本表和按版本迁移；初始化可重复执行，不以无版本的临时 `ALTER` 作为长期演进机制。
- 明确 JSONB、TIMESTAMPTZ、外键、唯一约束、索引和级联策略；SQLite/PG 的分页顺序、幂等和异常行为保持一致。
- 审核、拒绝、恢复、重试和 checkpoint 的状态、事件、产物、计数在单一事务中提交或回滚。
- Skill/Marketplace/MCP 高风险写动作继续经过现有 RBAC 与审计；Store 适配不得绕过 P0 权限控制。
- PostgreSQL 不可用时服务显式失败，不允许任何领域继续写 SQLite。

### 门禁

- 各领域 CRUD、分页、唯一/外键约束、幂等、重复初始化、事务回滚独立通过。
- 故障注入能证明审核/checkpoint 不产生半提交状态。
- RAG 集成由 `PersistenceStores` 创建，并与主 Store 使用同一目标库。

### 阶段 2 实施记录（2026-09-16）

- 已新增 `app/persistence/postgres_migrations.py`，以 `jaycode_schema_migration` 保存迁移版本、名称、校验值和执行时间；重复执行会跳过同校验值版本，历史名称或校验值漂移会明确失败。
- PostgreSQL 主 Store 的初始化已通过统一迁移执行器执行；Memory 与 PgVector RAG 的新实例已改为委托主 Store 的完整 Schema 入口，避免运行时分别创建不同 Schema。
- 已加入 pgvector 可用性预检查；不可用时 Schema 初始化失败，不会降级 SQLite。审核/checkpoint 现有单连接事务路径继续由 PostgreSQL Store 覆盖。
- CI PostgreSQL Job 已改为显式传递 `JAYCODE_TEST_DATABASE_URL`，并扩展执行 Task、Memory、RAG 与迁移测试；不会读取应用 `DATABASE_URL` 作为测试目标。
- 本机回归：`ruff check app tests` 通过；`pytest -q tests` 为 `57 passed, 9 skipped`。9 项跳过均为未设置隔离 PostgreSQL 测试 URL，未计为真实 PostgreSQL 契约通过。
- 2026-09-16 真实隔离 PostgreSQL 验证：`scripts/run_postgres_contracts.py` 自动创建随机 `jaycode_test_437e4eb5a92c4d7f99e10eb3de504b7a`，全部 `16 passed` 后自动删除。12 个领域均已提升为 `verified_stage2`，可进入阶段三共享契约与 API/Worker E2E。
- 本阶段未修改 `.env` 或迁移业务数据。

## 阶段 3：共用契约与 PostgreSQL API/Worker E2E

### 工作项

- 将 SQLite 和 PostgreSQL Store 契约参数化，共用同一断言集，不维护两套语义不同的测试。
- CI PostgreSQL Job 使用服务容器和独立测试数据库，真实运行契约；服务不可用时 job 失败或清晰 skip，绝不报告通过。
- 以隔离 PG 配置启动 API 和两个独立 Worker，验证：任务入队、唯一领取、心跳、取消、租约过期恢复、Worker 崩溃恢复、审核/checkpoint 恢复。
- 对 Task、Workflow、Review、Skill、MCP、Marketplace、Audit、Memory、LLM/Prompt、Benchmark、RAG 执行关键读写，并断言数据都落入同一个 PG 数据库。
- 验证 PG 连接断开会使 `/ready` 非就绪或服务启动失败，并通过 SQLite 数据库哈希/行数确认没有暗中写入。

### 命令与交付

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests -m "not postgres"
$env:JAYCODE_TEST_DATABASE_URL = "<只用于本机隔离 jaycode_test_* 数据库的连接串>"
.\.venv\Scripts\python.exe -m pytest -q tests -m postgres
```

实际测试标记以仓库 pytest 配置为准；若尚无 `postgres` marker，先补 marker 与安全 guard。报告需包含数据库名（不含凭据）、版本和结果。

### 门禁

- SQLite 与 PG 同一契约全过；API/Worker E2E 全过；两 Worker 无重复领取/丢失。
- P0 认证/RBAC、Marketplace、MCP、审计测试全过。
- 失败注入及连接失败测试通过。

### 阶段 3 实施记录（2026-09-16，已通过）

- 工厂已改为在全部领域标记为 `supported` 后构建完整 PostgreSQL Store bundle，并在应用启动检查中验证连接、Schema、pgvector 与主库/RAG 目标一致性；连接或初始化失败会明确失败，不会回退 SQLite。
- 已新增 PostgreSQL E2E 测试，覆盖 FastAPI `/health`、`/ready`、任务入队、读取与取消，以及两个独立进程对合成任务的唯一领取和完成写入。
- `scripts/run_postgres_contracts.py` 现会为子测试进程注入同一个随机 `jaycode_test_*` 主库与 RAG URL，并运行迁移、全域 Store 与 E2E 测试；它只删除本次成功创建的随机库。
- 2026-09-16 用户普通 PowerShell 运行隔离测试脚本：随机库 `jaycode_test_9574c30fd3424acd94cb569751e698fa` 执行完成后得到 `22 passed`，并由脚本自动删除。覆盖全域 PostgreSQL Store、迁移、SQLite/PostgreSQL 共享契约、API 入队/读取/取消/审核和双独立 Worker 唯一领取、checkpoint 恢复、租约恢复与心跳。
- 5 条 warning 均为 FastAPI/Starlette 生命周期函数 API 的弃用提示，不影响本阶段结果；它们应在后续 P2 生命周期重构中处理。
- 阶段三门禁已通过，但这只证明隔离 PostgreSQL 可运行；不得据此修改 `.env`、迁移现有 `data/dev_agent_studio.db` 或切换正式后端。下一步为阶段四的全量迁移工具、冲突保护和数据核验演练。

## 阶段 4：SQLite 全量迁移工具与隔离演练

### 工作项

- 固定源 Schema 版本及显式表/字段映射，覆盖盘点出的所有业务表；迁移前对实际表清单求差，任何新增未知表或字段立即中止。
- 将 SQLite 值确定性映射到 PG 类型；明确 BLOB、JSON、时间、序列/自增 ID、外键依赖顺序及循环依赖处理。
- 实现 CLI：只读 `--check`、一致性备份、源清单导出、目标预检查、`--import-postgres`、`--verify` 和脱敏报告。目标 URL 只从受控配置读取，报告从不包含连接串。
- 导入要求 PG 目标库为空或仅有兼容 schema 元数据；拒绝非预期业务表/行、主键冲突、重复源指纹和不兼容 Schema。
- 所有业务行导入在一个受控事务内完成；中断后整体回滚。记录源清单指纹，防止重复导入。
- 迁移前后逐表核对行数、主键集合摘要与规范化行哈希；验证数据库约束和关键查询。
- 只在合成 SQLite fixture 和随机临时 PG 库进行演练，测试成功导入、二次导入拒绝、冲突拒绝和故障回滚。

### 门禁

- 覆盖表数等于源清单表数；未知表/字段有负向测试。
- 临时库迁移前后所有表计数、主键摘要和规范化哈希一致。
- 重复导入、目标冲突、故障注入均不留下部分数据。
- 演练报告可复现且不含密钥。

### 阶段 4 实施记录（2026-09-16，已通过）

- `app/persistence/migration_mapping.py` 已建立当前 27 张业务表的严格 SQLite→PostgreSQL 映射清单；未映射表或列、缺失目标字段、无效 JSON 与不兼容 Schema 均会中止。
- `app/persistence/migrate.py` 已支持显式的隔离 `--check`、`--import-postgres`、`--verify`。阶段四目标只能从 `JAYCODE_MIGRATION_TARGET_URL` 读取，明确拒绝 `DATABASE_URL`、非 loopback 和非 `jaycode_test_*` 数据库。
- 导入会先初始化版本化目标 Schema、检查业务表为空、写入源快照指纹账本，并在单一事务中完成写入；核验比较映射后逐表行数和规范化行哈希。
- 已新增成功导入/核验、重复导入拒绝、未知表拒绝及无效 JSON 故障回滚测试，并接入随机 PostgreSQL 测试运行器和 CI PostgreSQL Job。
- 2026-09-16 用户普通 PowerShell 运行随机隔离 PostgreSQL 库 `jaycode_test_d5bf7b78209140c996bbba3e3bc8f8c7`，全部测试结果为 `25 passed`，并由运行器自动删除。已实际覆盖成功导入/逐表核验、重复导入保护、未知表拒绝、无效 JSON 的事务回滚，以及此前的 Store、API 与双 Worker 验证。
- 5 条 warning 均是 FastAPI/Starlette 生命周期 API 弃用提示，不影响阶段四门禁。
- 本阶段仅使用合成 SQLite 与随机测试库；未对真实业务 SQLite 数据库执行备份、导入或核验，也未修改 `.env`。下一步为阶段五的完整质量门禁汇总；正式数据迁移仍属于阶段六。

## 阶段 5：最终切换前质量门禁

按顺序完成并保存结果：

```text
Ruff → SQLite 全量 pytest → PostgreSQL 全域契约 → PostgreSQL API/Worker E2E
→ 隔离迁移演练 → P0 安全回归 → 离线 Gold Set/基线
→ TypeScript 检查 → 前端构建 → 旧标识/依赖安全扫描
```

门禁清单必须逐项写明命令、日期、提交版本、pass/fail/skip、日志位置。任何失败、skip 或未执行项都意味着**不得正式切换**。更新《项目优化推进.md》时只能依据可复现结果变更状态。

## 阶段 6：正式迁移与切换（前置门禁全通过后）

此阶段会写入真实数据库，需单独确认维护窗口并由操作者在目标库预检查后执行：

1. 停止 API、所有 Worker 和 Supervisor，确认无活动写入。
2. 创建不可覆盖的一致性 SQLite 备份及清单；复核备份恢复可读。
3. 只读检查 PostgreSQL 目标库；遇到非预期业务行、冲突或 schema 不匹配立即停止，不清理目标。
4. 正式导入并完成逐表核验；未完全匹配不改配置、不启动 PG 模式。
5. 通过核验后备份原 `.env`（权限受限、不纳入 Git），再将统一 Store 配置设为 PostgreSQL；不在文档、命令历史或日志中打印密码。
6. 启动 API/Worker，验证 `/health`、`/ready` 及所有业务域读写和审计；验证 PG 不可用时 fail-closed，SQLite 无新增写入。
7. 保留原 SQLite 数据库和备份。启动验证失败且 PG 尚无新业务写入时，回滚本次迁移并恢复 SQLite 配置；PG 已接受新写入后必须先冻结写入、完成对账及恢复方案，不可仅切换配置回滚。

## 最终验收与状态规则

只有所有阶段门禁通过、正式迁移数据核验一致、PostgreSQL 模式 API/Worker E2E 成功后，才可以在推进书中将“PostgreSQL 全域接入/迁移/切换”及剩余 P1 标记完成。否则明确写出已完成项、未完成项、被跳过项和阻塞原因；默认保持 SQLite。
