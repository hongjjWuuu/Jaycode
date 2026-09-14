# FastAPI 学习笔记

FastAPI 是一个用 Python 写的现代 Web 框架，主要用来快速构建 API 服务。

你可以把它理解成：

> Python 里的高效后端框架，专门擅长写接口、做参数校验、生成文档、处理异步请求。

## 1. FastAPI 是什么

FastAPI 的核心特点是：

- 写法简洁
- 类型提示友好
- 自动校验请求参数
- 自动生成 OpenAPI / Swagger 文档
- 原生支持异步
- 很适合做 API、Agent 后端、工具服务

它的本质是一个 **HTTP API 框架**，重点不是“渲染页面”，而是把业务能力快速暴露成可调用的 Web 接口。

---

## 2. FastAPI 在 Jaycode 里做什么

在 `Jaycode` 里，FastAPI 不是业务本体，而是 **服务外壳** 和 **接口入口层**。

### 2.1 应用入口

文件：

- [app/main.py](../../app/main.py)

职责：

- 创建 FastAPI 应用
- 挂载 API 路由
- 挂载前端静态资源
- 提供健康检查接口

示意：

```python
app = FastAPI(title=settings.app_name, version="0.1.0")
```

### 2.2 路由层

文件：

- [app/api/routes.py](../../app/api/routes.py)

职责：

- 暴露项目分析接口
- 暴露代码审查接口
- 暴露 RAG 接口
- 暴露 Skill 接口
- 暴露 MCP 接口
- 暴露 Workflow 接口
- 暴露 Task Runtime 接口
- 暴露 Benchmark 接口

### 2.3 数据模型层

文件：

- [app/schemas/project.py](../../app/schemas/project.py)
- [app/schemas/studio.py](../../app/schemas/studio.py)

职责：

- 定义请求模型
- 定义响应模型
- 做参数校验
- 形成稳定接口契约

### 2.4 配置层

文件：

- [app/core/config.py](../../app/core/config.py)

职责：

- 读取 `.env`
- 管理应用名、环境、模型、存储、sandbox、MCP 等配置
- 统一管理运行参数

---

## 3. FastAPI 的核心知识点

### 3.1 路由

FastAPI 用 `@app.get()`、`@app.post()` 或 `APIRouter` 来定义路由。

在 Jaycode 中：

- `app/main.py` 负责挂载路由
- `app/api/routes.py` 负责组织业务接口

常见接口示例：

- `/api/v1/projects/analyze`
- `/api/v1/tasks/run`
- `/api/v1/rag/query`
- `/api/v1/skills`
- `/api/v1/mcp/tools`
- `/api/v1/workflows/run`

### 3.2 请求校验

FastAPI 会根据 Pydantic 模型自动检查输入格式。

比如：

- `ProjectAnalyzeRequest`
- `RagQueryRequest`
- `TaskRunRequest`

如果字段缺失、类型错、范围不对，它会直接报错，不会让错误输入直接流进业务逻辑。

### 3.3 响应模型

通过 `response_model=...` 可以明确接口返回结构。

在项目里常见：

- `response_model=ProjectAnalyzeResponse`
- `response_model=TaskRunResponse`
- `response_model=BenchmarkRunResponse`

这样做的好处是：

- 返回结构稳定
- 自动文档清晰
- 前后端契约更明确

### 3.4 异常处理

FastAPI 常用 `HTTPException` 返回标准 HTTP 错误。

例如：

```python
raise HTTPException(status_code=404, detail="Task not found")
```

在 `Jaycode` 里，很多路由都会在参数不合法、资源不存在、权限不足时抛出这种异常。

### 3.5 流式返回

FastAPI 很适合做长任务流式输出。

项目里使用：

- `StreamingResponse`

适合：

- 项目分析过程推送
- 任务执行进度推送
- 多步骤 Agent 运行时的实时反馈

### 3.6 自动文档

FastAPI 会自动生成 OpenAPI / Swagger 文档。

这让接口天然具备：

- 可查看
- 可调试
- 可共享
- 可验证

---

## 4. Jaycode 里最典型的 FastAPI 路由

### 4.1 项目分析

接口：

- `/api/v1/projects/analyze`
- `/api/v1/projects/analyze/stream`

用途：

- 读取项目结构
- 生成技术栈分析
- 输出项目风险与建议

### 4.2 代码审查

接口：

- `/api/v1/code/review`

用途：

- 调用代码审查 Agent
- 结合项目扫描和审查逻辑生成结果

### 4.3 RAG

接口：

- `/api/v1/rag/process`
- `/api/v1/rag/ingest`
- `/api/v1/rag/query`
- `/api/v1/rag/documents`
- `/api/v1/rag/status`

用途：

- 文档加工
- 知识入库
- 检索查询
- ACL 管理
- Gold Case 评测

### 4.4 Skill

接口：

- `/api/v1/skills`
- `/api/v1/skills/{skill_code}/execute`
- `/api/v1/skills/{skill_code}/approval`
- `/api/v1/skills/{skill_code}/rollback`

用途：

- 管理 Skill 生命周期
- 支持审批、执行、启用、回滚

### 4.5 MCP

接口：

- `/api/v1/mcp/tools`
- `/api/v1/mcp/servers`
- `/api/v1/mcp/tools/call`
- `/api/v1/mcp/tool-call-logs`

用途：

- 管理 MCP 服务器
- 发现工具
- 审批工具调用
- 记录调用日志

### 4.6 Workflow

接口：

- `/api/v1/workflows`
- `/api/v1/workflows/run`
- `/api/v1/workflows/validate`

用途：

- 管理可视化工作流
- 验证工作流定义
- 执行工作流

### 4.7 Task Runtime

接口：

- `/api/v1/tasks/run`
- `/api/v1/tasks/run/stream`
- `/api/v1/tasks/{task_id}`
- `/api/v1/tasks/{task_id}/events`
- `/api/v1/tasks/{task_id}/report`
- `/api/v1/tasks/{task_id}/approve`
- `/api/v1/tasks/{task_id}/reject`
- `/api/v1/tasks/{task_id}/revise`

用途：

- 运行任务
- 查询事件
- 获取报告
- 支持人工审核和恢复

### 4.8 LLM Prompt 管理

接口：

- `/api/v1/llm/prompts`
- `/api/v1/llm/prompts/active`
- `/api/v1/llm/prompts/ab-test`
- `/api/v1/llm/traces`
- `/api/v1/llm/usage`

用途：

- 管理 Prompt 版本
- 做 Prompt A/B 测试
- 查看 LLM Trace 和使用情况

### 4.9 Benchmark

接口：

- `/api/v1/benchmarks/mcp/run`
- `/api/v1/benchmarks/llm/run`
- `/api/v1/benchmarks/rag/run`
- `/api/v1/benchmarks/workflow/run`
- `/api/v1/benchmarks/collaboration/run`

用途：

- 运行不同能力的评测
- 统计成功率、延迟、Token、成本等指标

---

## 5. FastAPI 和 Spring Boot 的类比

这是理解 FastAPI 最快的方式。

| FastAPI             | Spring Boot                                    | 作用          |
| ------------------- | ---------------------------------------------- | ----------- |
| `FastAPI()`         | `@SpringBootApplication`                       | 创建整个 Web 应用 |
| `APIRouter`         | `@RestController` + `@RequestMapping`          | 分组管理路由      |
| `@router.get/post`  | `@GetMapping / @PostMapping`                   | 定义接口        |
| `BaseModel`         | DTO / `@RequestBody` + Bean Validation         | 定义请求/响应模型   |
| `Field()`           | `@NotNull` / `@Size` / 默认值                     | 参数约束        |
| `HTTPException`     | `ResponseStatusException`                      | 返回 HTTP 错误  |
| `StreamingResponse` | SSE / 流式返回                                     | 边生成边返回      |
| `Depends()`         | `@Autowired` / 依赖注入                            | 依赖注入与复用     |
| `BaseSettings`      | `@ConfigurationProperties` / `application.yml` | 配置管理        |
| `StaticFiles`       | `ResourceHandler` / 静态资源映射                     | 挂载前端静态文件    |
| `Uvicorn`           | Tomcat / Undertow                              | 应用运行服务器     |

---

## 6. FastAPI 和 Spring Boot 的思维差异

### Spring Boot 更像“企业后端全家桶”

- 组件多
- 约定多
- 生态成熟
- 适合大型 Java 项目

### FastAPI 更像“轻量但现代的 API 框架”

- 写法更直接
- 类型提示驱动更强
- 参数校验和文档生成更自动化
- 很适合快速做服务和工具接口

---

## 7. 在 Jaycode 里学习 FastAPI 最值得看的主线

建议按这个顺序理解：

1. `app/main.py`：应用怎么创建、怎么挂载路由、怎么挂载前端
2. `app/api/routes.py`：接口怎么分模块组织
3. `app/schemas/*.py`：请求和响应模型怎么定义
4. `app/core/config.py`：环境变量和运行配置怎么管理
5. `StreamingResponse`：长任务和事件流怎么返回
6. `HTTPException`：错误怎么标准化处理

---

## 8. 学习时应该抓住的核心点

如果把 FastAPI 学习压缩成几个关键词，就是：

- 路由
- 校验
- 响应模型
- 异常处理
- 流式输出
- 配置管理
- 静态资源
- 自动文档

这些点在 Jaycode 里都能找到对应实现。

---

## 9. 一句话总结

FastAPI 是一个 **用 Python 快速构建 API 的框架**，在 Jaycode 里主要承担：

- 应用入口
- 路由组织
- 请求校验
- 响应建模
- 流式输出
- 配置管理
- 前端静态资源挂载

它把内部 Agent 能力包装成一个可调用、可文档化、可维护的 Web 服务。
