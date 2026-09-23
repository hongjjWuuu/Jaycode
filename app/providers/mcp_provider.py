from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agents.project_tools import EXCLUDED_DIRS
from app.core.config import settings
from app.core.observability import record_domain_operation
from app.core.security import execution_auth_context
from app.harness.events import utc_now_iso
from app.persistence.factory import get_persistence_stores


# 本地确定性适配器
#   - 用于开发、演示和回退
# 实现的是一套“MCP 风格”的本地工具
# 其实不是去连外部 MCP server，而是直接操作本地文件系统和 Git
class LocalMCPProvider:
    """Local deterministic MCP-shaped adapter kept as the default provider."""

    # 把传入的 root_path 转成绝对路径 检查它是不是目录 如果不是目录就报错
    def _root(self, root_path: str) -> Path:
        root = Path(root_path).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        return root

    # 检查路径不能越界：
    # 目标路径必须在 root 目录内
    # 不允许访问 root 外面的内容
    def _safe_target(self, root_path: str, path: str = ".") -> tuple[Path, Path]:
        root = self._root(root_path)
        # 检查目标是否仍然在 root 目录内
        target = (root / path).resolve()
        if target != root and root not in target.parents:
            raise PermissionError("Refusing to access outside root path")
        return root, target

    # 递归遍历 root 下所有文件
    # 跳过目录
    # 跳过排除目录
    # 返回文件相对路径列表
    def list_files(self, root_path: str, max_files: int = 200) -> dict[str, Any]:
        root = self._root(root_path)
        files = []
        for path in root.rglob("*"):
            if len(files) >= max_files:
                break
            if path.is_dir():
                continue
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
                continue
            files.append(path.relative_to(root).as_posix())
        return {"provider": "local", "root": root.as_posix(), "files": files}
    
    # 校验路径安全
    # 确认目标是文件
    # 读取文本内容
    # 截断到指定字符数
    def read_file(self, root_path: str, file_path: str, max_chars: int = 4000) -> dict[str, Any]:
        root, target = self._safe_target(root_path, file_path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        content = target.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        return {"provider": "local", "root": root.as_posix(), "path": target.relative_to(root).as_posix(), "content": content}

    # 列出某个目录下的直接子项
    # 返回每个子项的：名称
    # 相对路径
    # 类型（文件/目录）
    def list_directory(self, root_path: str, path: str = ".", limit: int = 100) -> dict[str, Any]:
        root, base = self._safe_target(root_path, path)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        entries = []
        for child in sorted(base.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
            if len(entries) >= limit:
                break
            if child.name in EXCLUDED_DIRS:
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": child.relative_to(root).as_posix(),
                    "type": "directory" if child.is_dir() else "file",
                }
            )
        return {"provider": "local", "root": root.as_posix(), "path": base.relative_to(root).as_posix() or ".", "entries": entries}

    # 用途 (把目录树拉出来,有深度、数量限制)
    # 快速了解项目结构
    # 生成目录树视图
    # 给分析器提供结构输入
    def directory_tree(self, root_path: str, path: str = ".", max_depth: int = 2, limit: int = 200) -> dict[str, Any]:
        root, base = self._safe_target(root_path, path)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        tree = []
        for child in base.rglob("*"):
            relative_to_base = child.relative_to(base)
            relative_to_root = child.relative_to(root)
            if any(part in EXCLUDED_DIRS for part in relative_to_root.parts):
                continue
            if len(relative_to_base.parts) > max_depth:
                continue
            tree.append(
                {
                    "path": relative_to_root.as_posix(),
                    "type": "directory" if child.is_dir() else "file",
                    "depth": len(relative_to_base.parts),
                }
            )
            if len(tree) >= limit:
                break
        return {"provider": "local", "root": root.as_posix(), "path": base.relative_to(root).as_posix() or ".", "tree": tree}

    # 在文件名和文本内容里搜索关键字query，返回匹配的路径和片段
    def search_files(self, root_path: str, query: str, path: str = ".", limit: int = 50) -> dict[str, Any]:
        root, base = self._safe_target(root_path, path)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        matches = []
        needle = query.lower()
        text_suffixes = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".json", ".css", ".html", ".yml", ".yaml"}
        for child in base.rglob("*"):
            if len(matches) >= limit:
                break
            if not child.is_file():
                continue
            relative = child.relative_to(root)
            if any(part in EXCLUDED_DIRS for part in relative.parts):
                continue
            relative_text = relative.as_posix()
            matched = needle in relative_text.lower()
            snippet = ""
            if not matched and child.suffix.lower() in text_suffixes:
                text = child.read_text(encoding="utf-8", errors="ignore")
                index = text.lower().find(needle)
                matched = index >= 0
                if matched:
                    snippet = text[max(0, index - 80) : index + 160]
            if matched:
                matches.append({"path": relative_text, "snippet": snippet})
        return {"provider": "local", "root": root.as_posix(), "query": query, "matches": matches}

    # 看仓库有没有未提交修改，看当前变更概况
    def git_status(self, repo_path: str) -> dict[str, Any]:
        root = Path(repo_path).expanduser().resolve()
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return {
            "provider": "local",
            "repo": root.as_posix(),
            "returncode": result.returncode,
            "stdout": result.stdout.splitlines(),
            "stderr": result.stderr,
        }

    # 看最近提交历史,快速判断项目演变情况
    def git_log(self, repo_path: str, limit: int = 10) -> dict[str, Any]:
        root = Path(repo_path).expanduser().resolve()
        result = subprocess.run(
            ["git", "-C", str(root), "log", f"-{limit}", "--oneline"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return {
            "provider": "local",
            "repo": root.as_posix(),
            "returncode": result.returncode,
            "commits": result.stdout.splitlines(),
            "stderr": result.stderr,
        }

# 真正的 stdio MCP client
#  - 支持 server 配置、工具发现、调用、日志、审批
class RealMCPProvider:
    """Minimal stdio MCP client.

    It intentionally opens a short-lived connection per operation. That keeps the
    runtime deterministic for the current FastAPI app while still speaking the
    real MCP JSON-RPC protocol over stdio.
    """

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[2]

    # 从 task_store 里拿 MCP server 和工具的数量
    # 返回当前 provider 状态
    def status(self) -> dict[str, Any]:
        servers = get_persistence_stores().mcp.list_mcp_servers()
        tools = get_persistence_stores().mcp.list_mcp_tools()
        return {
            "provider": "mcp",
            "server_count": len(servers),
            "enabled_servers": len([item for item in servers if item.get("enabled")]),
            "tool_count": len(tools),
        }

    # MCP 管理页保存 server 配置；把 server 配置存入数据库
    def save_server(self, server: dict[str, Any]) -> dict[str, Any]:
        if str(server.get("transport") or "stdio") == "stdio":
            self._validate_server_process_config(server)
        return get_persistence_stores().mcp.save_mcp_server(server)

    # 前端 MCP 页面加载 server 列表；列出已保存的 MCP server
    def list_servers(self) -> list[dict[str, Any]]:
        return get_persistence_stores().mcp.list_mcp_servers()

    # 启用或禁用某个 server 
    # enabled=True 时状态变成 "enabled" 否则变成 "disabled"
    def set_server_enabled(self, server_id: str, enabled: bool) -> dict[str, Any] | None:
        if enabled:
            server = get_persistence_stores().mcp.get_mcp_server(server_id)
            if not server:
                return None
            self._validate_server_process_config(server)
        status = "enabled" if enabled else "disabled"
        return get_persistence_stores().mcp.update_mcp_server_status(server_id, status, None, enabled=enabled)

    # 找到 server
    # 检查是否有效
    # 通过 MCP 协议发 tools/list
    # 把返回的工具保存到数据库
    # 清理不再存在的工具
    # 更新 server 状态
    def discover_tools(self, server_id: str) -> dict[str, Any]:
        server = self._enabled_server(server_id, require_enabled=False)
        started = time.perf_counter()
        try:
            result, _ = self._request(server, "tools/list", {})
            tools = result.get("tools") if isinstance(result, dict) else []
            saved = []
            discovered_names: set[str] = set()
            for tool in tools or []:
                if not isinstance(tool, dict):
                    continue
                name = str(tool.get("name") or "").strip()
                if not name:
                    continue
                discovered_names.add(name)
                saved.append(
                    get_persistence_stores().mcp.upsert_mcp_tool(
                        {
                            "server_id": server_id,
                            "name": name,
                            "description": tool.get("description"),
                            "input_schema": tool.get("inputSchema") or tool.get("input_schema") or {},
                            "enabled": True,
                            "status": "available",
                        }
                    )
                )
            get_persistence_stores().mcp.prune_mcp_tools(server_id, discovered_names)
            get_persistence_stores().mcp.update_mcp_server_status(server_id, "connected", None)
            return {"server_id": server_id, "status": "connected", "tools": saved, "latency_ms": self._elapsed_ms(started)}
        except Exception as exc:
            get_persistence_stores().mcp.update_mcp_server_status(server_id, "failed", str(exc))
            raise
    
    # 从数据库里列出已注册工具 MCP 管理页展示工具 后续做审批前先看有哪些工具
    def list_tools(self, server_id: str | None = None) -> list[dict[str, Any]]:
        return get_persistence_stores().mcp.list_mcp_tools(server_id)
 
    # 启用或禁用某个工具 启用/禁用是工具是否可用 审批是某个 agent 能不能用
    def set_tool_enabled(self, server_id: str, tool_name: str, enabled: bool) -> dict[str, Any] | None:
        return get_persistence_stores().mcp.update_mcp_tool_enabled(server_id, tool_name, enabled)
 
    # 给某个 agent 对某个 tool 写审批记录 
    def set_approval(self, agent_code: str, server_id: str, tool_name: str, allowed: bool, reason: str | None = None) -> dict[str, Any]:
        return get_persistence_stores().mcp.set_mcp_tool_approval(agent_code, server_id, tool_name, allowed, reason)

    # 去数据库查这个 agent 对这个工具是否有审批 在真正调用工具前做权限检查
    def check_approval(self, agent_code: str, server_id: str, tool_name: str) -> dict[str, Any]:
        approval = get_persistence_stores().mcp.get_mcp_tool_approval(agent_code, server_id, tool_name)
        allowed = bool(approval and approval.get("allowed"))
        reason = approval.get("reason") if approval else "MCP tool has not been approved for this agent."
        return {"agent_code": agent_code, "server_id": server_id, "tool_name": tool_name, "allowed": allowed, "reason": reason}

# 生成 call_id
# 记录开始时间
# 找 server
# 找 tool
# 看 tool 是否禁用
# 检查审批
# 通过 MCP 协议发起 tools/call
# 保存调用日志
# 返回结果

# 工具是否存在
# 工具是否启用
# 当前身份是否被批准
# 工具调用结果是什么
# 调用了多久
# 是否失败
# 这就是治理链路。
    def call_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any] | None = None, agent_code: str = "workflow_runner") -> dict[str, Any]:
        call_id = f"mcp_call_{uuid4().hex}"
        started = time.perf_counter()
        arguments = arguments or {}
        try:
            server = self._enabled_server(server_id)
            tool = get_persistence_stores().mcp.get_mcp_tool(server_id, tool_name)
            if tool and not tool.get("enabled"):
                raise PermissionError(f"MCP tool disabled: {server_id}:{tool_name}")
            approval = self.check_approval(agent_code, server_id, tool_name)
            if not approval["allowed"]:
                raise PermissionError(str(approval["reason"]))
            result, exit_code = self._request(
                server,
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            output = {"provider": "mcp", "server_id": server_id, "tool_name": tool_name, "result": result}
            mcp_error = self._mcp_error_message(result)
            context = execution_auth_context()
            get_persistence_stores().mcp.save_mcp_call_log(
                {
                    "call_id": call_id,
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "agent_code": agent_code,
                    "input": self._redact(arguments),
                    "output": output,
                    "status": "failed" if mcp_error else "completed",
                    "error_message": mcp_error,
                    "latency_ms": self._elapsed_ms(started),
                    "request_id": context.request_id if context else "",
                    "actor_id": context.actor_id if context else "internal",
                    "role": context.role if context else "system-agent",
                    "command_summary": Path(str(server["command"])).name,
                    "exit_code": exit_code,
                    "created_at": utc_now_iso(),
                }
            )
            record_domain_operation("mcp", "call_tool", started, status="failed" if mcp_error else "success", error_code="MCP_ERROR" if mcp_error else "")
            return {**output, "call_id": call_id, "status": "failed" if mcp_error else "completed", "error_message": mcp_error}
        except Exception as exc:
            context = execution_auth_context()
            server = get_persistence_stores().mcp.get_mcp_server(server_id) or {}
            get_persistence_stores().mcp.save_mcp_call_log(
                {
                    "call_id": call_id,
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "agent_code": agent_code,
                    "input": self._redact(arguments),
                    "output": {},
                    "status": "failed",
                    "error_message": str(exc),
                    "latency_ms": self._elapsed_ms(started),
                    "request_id": context.request_id if context else "",
                    "actor_id": context.actor_id if context else "internal",
                    "role": context.role if context else "system-agent",
                    "command_summary": Path(str(server.get("command") or "")).name,
                    "exit_code": None,
                    "created_at": utc_now_iso(),
                }
            )
            record_domain_operation("mcp", "call_tool", started, status="failed", error_code=type(exc).__name__)
            raise

    def list_call_logs(self, limit: int = 100, server_id: str | None = None) -> list[dict[str, Any]]:
        return get_persistence_stores().mcp.list_mcp_call_logs(limit=limit, server_id=server_id)

    # 如果 MCP 返回 isError=true
    # 尝试从返回内容里提取错误文本
    def _mcp_error_message(self, result: dict[str, Any]) -> str | None:
        if not result.get("isError"):
            return None
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    return item["text"]
        return "MCP tool returned isError=true"

    # 校验 server 是否存在
    # 是否启用
    # 是否使用 stdio
    # 是否配置了 command
    def _enabled_server(self, server_id: str, *, require_enabled: bool = True) -> dict[str, Any]:
        server = get_persistence_stores().mcp.get_mcp_server(server_id)
        if not server:
            raise KeyError(f"MCP server not found: {server_id}")
        if require_enabled and not server.get("enabled"):
            raise PermissionError(f"MCP server disabled: {server_id}")
        if server.get("transport") != "stdio":
            raise NotImplementedError("Only stdio MCP transport is supported in this phase")
        if not server.get("command"):
            raise ValueError("MCP stdio server command is required")
        self._validate_server_process_config(server)
        return server

    def _validate_server_process_config(self, server: dict[str, Any]) -> None:
        command = str(server.get("command") or "").strip()
        allowed = {item.strip().lower() for item in settings.jaycode_mcp_allowed_commands.split(",") if item.strip()}
        if not allowed or Path(command).name.lower() not in allowed:
            raise PermissionError("MCP command is not in JAYCODE_MCP_ALLOWED_COMMANDS")
        args = server.get("args") or []
        if not isinstance(args, list) or any(not isinstance(item, str) or not item.strip() for item in args):
            raise ValueError("MCP args must be a non-empty string array")
        dangerous = ("&&", "||", ";", "|", "$(", "\r", "\n")
        shell_flags = {"-c", "/c", "/k", "-command", "-encodedcommand"}
        if any(item.lower() in shell_flags or any(token in item for token in dangerous) for item in args):
            raise PermissionError("Shell-style MCP arguments are not allowed")
        env = server.get("env") or {}
        if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()):
            raise ValueError("MCP env must be a string-to-string object")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in env):
            raise ValueError("MCP env contains an invalid variable name")
        protected = {"PATH", "PATHEXT", "PYTHONPATH", "NODE_OPTIONS", "LD_PRELOAD", "COMSPEC", "SHELL"}
        if protected.intersection(key.upper() for key in env):
            raise PermissionError("MCP env cannot override protected runtime variables")

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if any(token in key.lower() for token in ("token", "secret", "password", "api_key", "apikey")) else self._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value


    # 协议通信核心 
# 拼出命令行
# 合并环境变量
# 启动外部进程
# 开线程读 stdout / stderr
# 发 initialize
# 收初始化响应
# 发 notifications/initialized
# 再发真正的 method 请求
# 等待响应
# 超时或异常则报错
# 最后终止进程

    def _request(self, server: dict[str, Any], method: str, params: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
        self._validate_server_process_config(server)
        request_id = f"mcp_worker_{uuid4().hex}"
        worker_env = os.environ.copy()
        worker_env.update({
            "JAYCODE_MCP_ALLOWED_COMMANDS": settings.jaycode_mcp_allowed_commands,
            "JAYCODE_MCP_MAX_RUNTIME_SECONDS": str(settings.jaycode_mcp_max_runtime_seconds),
            "JAYCODE_MCP_MAX_OUTPUT_BYTES": str(settings.jaycode_mcp_max_output_bytes),
            "JAYCODE_REQUEST_ID": request_id,
        })
        payload = json.dumps({"server": server, "method": method, "params": params, "request_id": request_id}, ensure_ascii=False, separators=(",", ":"))
        process = subprocess.Popen(
            [sys.executable, "-m", "app.providers.mcp_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self.project_root),
            env=worker_env,
            shell=False,
        )
        try:
            output, stderr = process.communicate(payload + "\n", timeout=float(max(1, settings.jaycode_mcp_max_runtime_seconds)) + 2)
            if process.returncode != 0:
                detail = (output or stderr or "MCP worker failed").strip()[-2000:]
                raise RuntimeError(detail)
            response = json.loads((output or "").strip().splitlines()[-1])
            if not response.get("ok"):
                raise RuntimeError(str(response.get("error") or "MCP worker failed"))
            result = response.get("result")
            return (result if isinstance(result, dict) else {"result": result}), process.returncode
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise TimeoutError("MCP Worker request timed out") from exc
        finally:
            self._stop_process(process)

    def _stop_process(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=1)
            except Exception:  # noqa: BLE001 - process cleanup must continue through termination failures
                return
        except Exception:  # noqa: BLE001 - process cleanup is best effort after request completion
            return

    # 把 JSON payload 写到子进程 stdin
    def _write_message(self, process: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
        if not process.stdin:
            raise RuntimeError("MCP process stdin is not available")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        process.stdin.write(body + b"\n")
        process.stdin.flush()

    # 从消息队列里等指定 request_id 的响应 如果超时，抛出 TimeoutError
    # 消息里有 error，直接抛异常 如果返回 result 不是 dict，就包一层
    def _read_response(
        self,
        messages: queue.Queue[dict[str, Any] | None],
        request_id: int,
        stderr_chunks: list[bytes],
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        timeout_seconds = float(timeout_seconds or settings.jaycode_mcp_max_runtime_seconds)
        while time.perf_counter() - started < timeout_seconds:
            try:
                message = messages.get(timeout=0.25)
            except queue.Empty:
                continue
            if not message:
                continue
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
            result = message.get("result")
            return result if isinstance(result, dict) else {"result": result}
        stderr = b"".join(stderr_chunks).decode("utf-8", errors="ignore")
        raise TimeoutError(f"MCP request timed out: {stderr}")

# 后台线程不断读取消息
# 读到消息就放进队列
# 读不到就结束
    def _read_messages(self, process: subprocess.Popen[bytes], messages: queue.Queue[dict[str, Any] | None]) -> None:
        while True:
            try:
                message = self._read_message(process)
            except Exception:  # noqa: BLE001 - reader terminates when the child protocol fails
                message = None
            if not message:
                messages.put(None)
                return
            messages.put(message)

    # 解析 MCP 消息 
    # 兼容两种情况：1.直接 JSON 行 2.Content-Length 风格的 MCP 协议消息
    def _read_message(self, process: subprocess.Popen[bytes]) -> dict[str, Any] | None:
        if not process.stdout:
            raise RuntimeError("MCP process stdout is not available")
        first_line = process.stdout.readline()
        if not first_line:
            return None
        if not first_line.lower().startswith(b"content-length:"):
            if len(first_line) > settings.jaycode_mcp_max_output_bytes:
                raise ValueError("MCP output exceeded configured limit")
            text = first_line.decode("utf-8", errors="ignore").strip()
            if not text:
                return None
            return json.loads(text)
        headers: dict[str, str] = {}
        text = first_line.decode("ascii", errors="ignore").strip()
        key, value = text.split(":", 1)
        headers[key.lower()] = value.strip()
        while True:
            line = process.stdout.readline()
            if not line:
                return None
            if line in {b"\r\n", b"\n"}:
                break
            text = line.decode("ascii", errors="ignore").strip()
            if ":" in text:
                key, value = text.split(":", 1)
                headers[key.lower()] = value.strip()
        length = int(headers.get("content-length") or 0)
        if length <= 0:
            return None
        if length > settings.jaycode_mcp_max_output_bytes:
            raise ValueError("MCP output exceeded configured limit")
        body = process.stdout.read(length)
        if len(body) > settings.jaycode_mcp_max_output_bytes:
            raise ValueError("MCP output exceeded configured limit")
        return json.loads(body.decode("utf-8"))

# 单独读取子进程 stderr
# 供超时或错误时辅助诊断
    def _read_stderr(self, process: subprocess.Popen[bytes], stderr_chunks: list[bytes]) -> None:
        if not process.stderr:
            return
        while True:
            chunk = process.stderr.readline()
            if not chunk:
                return
            current = sum(len(item) for item in stderr_chunks)
            if current < settings.jaycode_mcp_max_output_bytes:
                stderr_chunks.append(chunk[: settings.jaycode_mcp_max_output_bytes - current])

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))

# 对外只暴露一套调用方式，底层到底是 local 还是 real，不让上层知道
class MCPProvider:
    """Facade selected by JAYCODE_MCP_PROVIDER=local|mcp."""

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        self.env_path = self.project_root / ".env"
        self.local = LocalMCPProvider()
        self.real = RealMCPProvider()

    # 读取 JAYCODE_MCP_PROVIDER
    # 如果环境变量没设置，就读 .env
    # 再不行默认 local
    @property
    def provider_kind(self) -> str:
        return (os.getenv("JAYCODE_MCP_PROVIDER") or self._read_env_file().get("JAYCODE_MCP_PROVIDER") or "local").strip().lower()
    
    # 如果是 mcp，返回真实状态 否则返回本地模式状态
    def status(self) -> dict[str, Any]:
        if self.provider_kind == "mcp":
            return self.real.status()
        return {"provider": "local", "server_count": 0, "tool_count": 4}

    # 这几个方法都直接转给 LocalMCPProvider
    def list_files(self, root_path: str, max_files: int = 200) -> dict[str, Any]:
        return self.local.list_files(root_path, max_files)

    def read_file(self, root_path: str, file_path: str, max_chars: int = 4000) -> dict[str, Any]:
        return self.local.read_file(root_path, file_path, max_chars)

    def git_status(self, repo_path: str) -> dict[str, Any]:
        return self.local.git_status(repo_path)

    def git_log(self, repo_path: str, limit: int = 10) -> dict[str, Any]:
        return self.local.git_log(repo_path, limit)

    # 分流核心
    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None, *, server_id: str | None = None, agent_code: str = "workflow_runner") -> dict[str, Any]:
        if self.provider_kind == "mcp":
            if not server_id:
                raise ValueError("server_id is required when JAYCODE_MCP_PROVIDER=mcp")
            return self.real.call_tool(server_id, tool_name, arguments, agent_code=agent_code)
        return self._call_local_tool(tool_name, arguments or {})

    # 本地工具名映射
    # 没有真实 MCP server，系统也能用“工具名”调用本地能力
    def _call_local_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        root_path = str(arguments.get("root_path") or arguments.get("repo_path") or ".")
        if tool_name in {"filesystem.read", "read_file"}:
            return self.read_file(root_path, str(arguments.get("file_path") or arguments.get("path") or "README.md"), int(arguments.get("max_chars") or 4000))
        if tool_name in {"filesystem.list", "list_directory"}:
            if "path" in arguments:
                return self.local.list_directory(root_path, str(arguments.get("path") or "."), int(arguments.get("limit") or 100))
            return self.list_files(root_path, int(arguments.get("max_files") or arguments.get("limit") or 200))
        if tool_name == "directory_tree":
            return self.local.directory_tree(root_path, str(arguments.get("path") or "."), int(arguments.get("max_depth") or 2), int(arguments.get("limit") or 200))
        if tool_name == "search_files":
            return self.local.search_files(root_path, str(arguments.get("query") or ""), str(arguments.get("path") or "."), int(arguments.get("limit") or 50))
        if tool_name == "git.status":
            return self.git_status(root_path)
        if tool_name == "git.log":
            return self.git_log(root_path, int(arguments.get("limit") or 10))
        return self.list_files(root_path, int(arguments.get("max_files") or 200))

    def _read_env_file(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in self.env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values


mcp_provider = MCPProvider()
