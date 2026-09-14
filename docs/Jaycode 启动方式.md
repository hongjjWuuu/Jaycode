# Jaycode 启动方式

当前项目的主入口是：

```text
.\app\main.py
```

## 一、最简单启动版

适合先确认后端能否正常启动。

### 1. 进入项目目录

```powershell
cd /d .
```

如果你在 PowerShell 里，也可以用：

```powershell
Set-Location .
```

### 2. 启动后端

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

### 3. 检查健康状态

打开：

```text
http://127.0.0.1:8100/health
```

如果返回类似下面内容，说明后端已正常启动：

```json
{
  "status": "ok",
  "app": "Jaycode",
  "env": "dev"
}
```

## 二、推荐启动版

如果你想一次性完成前后端启动，使用：

```powershell
cd .
powershell -ExecutionPolicy Bypass -File .\setup-and-start.ps1
```

这个脚本会依次做：

1. 检查 `.env`
2. 检查必需配置
3. 准备 Python 环境
4. 安装 Python 依赖
5. 检查 Node.js 和 npm
6. 安装前端依赖
7. 构建前端 `web/dist`
8. 启动后端
9. 通过 FastAPI 托管前端页面

启动成功后访问：

```text
http://127.0.0.1:8100/
```

## 三、前端单独启动

如果你只想调试前端：

```powershell
cd web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

访问：

```text
http://127.0.0.1:5173/
```

## 四、完整功能需要什么

如果你想启用更多能力，通常需要按这个顺序准备：

1. 填好真实的 `OPENAI_API_KEY`
2. 确认 `OPENAI_BASE_URL` 和 `JAYCODE_AGENT_LLM`
3. 保持 `JAYCODE_MEMORY_EXTRACTOR=rule` 或切换成 `llm`
4. 需要更强检索时再启用 PgVector
5. 需要真实工具调用时再切换 MCP Provider
6. 需要更强隔离时再启用 Docker Skill Sandbox

## 五、最常用检查命令

```powershell
cd .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

```powershell
cd web
npm run build
```

```powershell
cd .
powershell -ExecutionPolicy Bypass -File .\setup-and-start.ps1
```
