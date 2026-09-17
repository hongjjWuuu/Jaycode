# Jaycode 外部 Skill 接入说明 + MCP 接入说明

这份说明面向两类接入：

1. 外部 Skill 包接入 Jaycode
2. 外部 MCP Server 接入 Jaycode

它们都能把外部能力带进 Jaycode，但定位不同：

- Skill 更像“可安装的能力模块”
- MCP 更像“可连接的外部工具总线”

---

## 一、先说结论

### 1. Skill 能不能从外部接入？

可以。

Jaycode 允许把外部 Skill 以 package 的形式安装进来，安装后它会进入系统的技能注册、审批、执行日志、版本管理流程，而不是只停留在文件层面。

### 2. MCP 工具能不能从外部接入？

可以，而且 MCP 本身就是为外部工具接入准备的。

你可以把外部 MCP Server 配到 Jaycode 里，再让系统自动发现它暴露的工具，完成审批后调用。

---

## 二、Skill 是怎么接入的

Jaycode 里的 Skill 不是简单脚本，而是统一能力对象。

### 1. Skill 的基础定义

Skill 的标准接口在这里：

- [app/skills/base.py](../../app/skills/base.py)

核心是两部分：

- `SkillContext`
- `Skill.execute(context, input_data)`

这意味着 Skill 在运行时会拿到统一上下文，而不是随意传参。

### 2. Skill 的注册

Skill 注册在这里：

- [app/skills/registry.py](../../app/skills/registry.py)

这里的 `skill_registry` 负责：

- 收集技能
- 查询技能
- 统一执行技能

对于代码层来说，业务不需要直接依赖具体实现，只要通过 registry 找到 skill_code 就行。

### 3. 内置 Skill 如何进入数据库

内置 Skill 会在运行前被种入数据库：

- [app/skills/executor.py](../../app/skills/executor.py)

`ensure_builtin_skills_seeded()` 的作用就是把内置 Skill 写入 SQLite。

这样做的好处是：

- 前端可以列出技能
- 审批系统可以管理技能权限
- 执行日志可以落库
- 版本管理和卸载也能统一处理

### 4. Skill 的执行流程

仍然在：

- [app/skills/executor.py](../../app/skills/executor.py)

`execute_skill()` 这条链路大致是：

1. 先保证内置 Skill 已种入数据库
2. 从数据库读取目标 Skill
3. 检查是否启用
4. 检查是否需要审批
5. 校验 Skill contract
6. 检查依赖
7. 执行 Skill
8. 记录执行日志

这说明 Skill 的接入不是“装进去就完了”，而是会进入治理链路。

### 5. Skill 在工作流里怎么被调用

工作流编译器会直接调用 Skill：

- [app/graphs/workflow_compiler.py](../../app/graphs/workflow_compiler.py)

当节点类型是 `skill` 时，工作流会走 `execute_skill(...)`。

也就是说，Skill 不只是 UI 里能点一下运行，它还能成为工作流节点的一部分。

### 6. 外部 Skill 怎么接入

外部 Skill 主要通过 marketplace 安装进入系统：

- [app/marketplace/installer.py](../../app/marketplace/installer.py)

支持的思路是：

- 外部包提供 manifest
- manifest 里描述 package_type
- 如果是 `skill_pack`，就把技能标准化
- 再写入系统内部存储

安装后的 Skill 会拥有：

- 技能记录
- 权限/审批
- 执行日志
- 版本信息

### 7. Skill 接入时你要关注什么

如果你要把别人写好的 Skill 接进 Jaycode，重点看这些字段和约束：

- `code`
- `name`
- `description`
- `execution_type`
- `permissions`
- `input_schema`
- `output_schema`
- `dependencies`
- `default_input`
- `entrypoint`

如果是 marketplace 包，还要保证：

- manifest 合法
- package_type 是 `skill_pack`
- contract 校验通过
- 依赖能解析

---

## 三、MCP 是怎么接入的

MCP 在 Jaycode 里是工具接入层，不是 Skill 层。

### 1. MCP 的 provider

入口在这里：

- [app/providers/mcp_provider.py](../../app/providers/mcp_provider.py)

这里有两种模式：

- `local`
- `mcp`

#### local 模式

这是本地确定性适配器，主要用于：

- 文件系统
- Git
- 本地演示

#### mcp 模式

这是标准 MCP server 接入模式，会通过 stdio 与外部 MCP Server 通讯。

### 2. MCP Server 是怎么接入的

MCP 的外部接入流程一般是：

1. 在 Jaycode 中保存 server 配置
2. 发现 server 暴露的工具
3. 把工具注册到数据库
4. 给 agent 配置审批
5. 调用工具
6. 记录调用日志

这整条链路都在：

- [app/providers/mcp_provider.py](../../app/providers/mcp_provider.py)

### 3. MCP 工具怎么执行

MCP 工具在工作流里也能被调用：

- [app/graphs/workflow_compiler.py](../../app/graphs/workflow_compiler.py)

当节点类型是 `mcp_tool` 时，工作流会调用 `mcp_provider.call_tool(...)`。

所以 MCP 工具不仅能在管理界面里配置，也能直接进入任务执行流。

### 4. MCP 的审批和日志

MCP 的治理点比较完整：

- server 是否启用
- tool 是否启用
- tool 是否被某个 agent 允许
- 每次调用是否记录日志

这些数据会落到 SQLite：

- [app/persistence/sqlite_store.py](../../app/persistence/sqlite_store.py)

### 5. 外部 MCP 能力是否支持

支持。

只要你有一个外部 MCP Server，Jaycode 就可以把它作为远端工具源接入。

这和 Skill 有点像，但层级不同：

- Skill 是“安装进来的能力模块”
- MCP 是“连进来的外部工具服务器”

---

## 四、Skill 和 MCP 的区别

| 维度 | Skill | MCP |
|---|---|---|
| 本质 | 能力模块 | 外部工具协议层 |
| 目标 | 把一个功能装进平台 | 把外部工具连进平台 |
| 管理对象 | 技能、版本、审批、执行日志 | server、tool、审批、调用日志 |
| 执行方式 | `execute_skill()` | `call_tool()` |
| 是否可外部接入 | 可以 | 可以，而且更天然 |
| 适合场景 | 业务功能复用 | 外部系统工具接入 |

---

## 五、外部 Skill 的典型接入方式

### 方式 A：市场包安装

这是最推荐的方式。

流程：

1. 外部作者准备 Skill 包
2. 包里提供 manifest
3. Jaycode 安装包
4. 系统验证 contract
5. 注册到技能库
6. 进入审批和日志链路

### 方式 B：系统内置开发

如果你自己开发 Skill，可以：

1. 先实现 Skill 协议
2. 再在 registry 里注册
3. 然后让它种入数据库

这适合你在项目内继续扩展平台能力。

---

## 六、外部 MCP 的典型接入方式

### 方式 A：注册远端 Server

流程：

1. 配置 MCP server
2. 发现工具
3. 启用工具
4. 为 agent 设审批
5. 调用工具

### 方式 B：marketplace 提供 MCP pack

Jaycode 的 marketplace 也支持 `mcp_pack`。

这意味着你可以通过包把一组 MCP server 预置进系统。

---

## 七、你应该怎么理解它们

如果你在做 Jaycode 平台化，可以这样理解：

- Skill 是平台内部能力单元
- MCP 是平台外部工具接入层
- marketplace 是两者的分发入口
- SQLite 是治理和状态中心
- workflow 是统一调度入口

---

## 八、实际使用建议

### 如果你要接入别人写好的功能

优先考虑 Skill。

因为它更像“可安装功能包”，安装后就能进入审批、执行、版本管理。

### 如果你要接入现成工具系统

优先考虑 MCP。

因为 MCP 更适合把外部系统工具直接接到 Jaycode 里。

### 如果你想让它们都可审计、可回滚、可追踪

就要保证：

- 记录进 SQLite
- 有审批记录
- 有执行日志
- 有版本信息

这也是 Jaycode 现在走向“平台化”最关键的一步。

---

## 九、对应代码入口速查

- Skill 定义: [app/skills/base.py](../../app/skills/base.py)
- Skill 注册: [app/skills/registry.py](../../app/skills/registry.py)
- Skill 执行: [app/skills/executor.py](../../app/skills/executor.py)
- Skill 安装: [app/marketplace/installer.py](../../app/marketplace/installer.py)
- MCP provider: [app/providers/mcp_provider.py](../../app/providers/mcp_provider.py)
- 工作流编译: [app/graphs/workflow_compiler.py](../../app/graphs/workflow_compiler.py)
- API 路由: [app/api/routes/](../../app/api/routes/__init__.py)
- 数据库存储: [app/persistence/sqlite_store.py](../../app/persistence/sqlite_store.py)
