from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

MAX_OUTPUT = 1024 * 1024
MAX_RUNTIME = 15


def _max_output() -> int:
    try:
        return max(1, int(os.getenv("JAYCODE_MCP_MAX_OUTPUT_BYTES", str(MAX_OUTPUT))))
    except ValueError:
        return MAX_OUTPUT


def _max_runtime() -> int:
    try:
        return max(1, int(os.getenv("JAYCODE_MCP_MAX_RUNTIME_SECONDS", str(MAX_RUNTIME))))
    except ValueError:
        return MAX_RUNTIME


def _validate(server: dict[str, Any]) -> None:
    command = str(server.get("command") or "").strip()
    allowed = {item.strip().lower() for item in os.getenv("JAYCODE_MCP_ALLOWED_COMMANDS", "").split(",") if item.strip()}
    if not allowed or Path(command).name.lower() not in allowed:
        raise PermissionError("MCP command is not in JAYCODE_MCP_ALLOWED_COMMANDS")
    args = server.get("args") or []
    if not isinstance(args, list) or any(not isinstance(item, str) or not item.strip() for item in args):
        raise ValueError("MCP args must be a string array")
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


def _write(process: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
    if not process.stdin:
        raise RuntimeError("MCP stdin is unavailable")
    process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
    process.stdin.flush()


def _read_message(process: subprocess.Popen[bytes]) -> dict[str, Any] | None:
    if not process.stdout:
        raise RuntimeError("MCP stdout is unavailable")
    first = process.stdout.readline()
    if not first:
        return None
    if not first.lower().startswith(b"content-length:"):
        if len(first) > _max_output():
            raise ValueError("MCP output exceeded configured limit")
        return json.loads(first.decode("utf-8", errors="ignore").strip())
    headers: dict[str, str] = {}
    while first and first not in {b"\r\n", b"\n"}:
        line = first.decode("ascii", errors="ignore").strip()
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
        first = process.stdout.readline()
    length = int(headers.get("content-length") or 0)
    if length <= 0 or length > _max_output():
        raise ValueError("MCP output exceeded configured limit")
    body = process.stdout.read(length)
    if len(body) > _max_output():
        raise ValueError("MCP output exceeded configured limit")
    return json.loads(body.decode("utf-8"))


def _serve(server: dict[str, Any], method: str, params: dict[str, Any]) -> dict[str, Any]:
    _validate(server)
    command = [str(server["command"]), *server.get("args", [])]
    env = os.environ.copy()
    env.update(server.get("env") or {})
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env)
    messages: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def reader() -> None:
        try:
            while True:
                message = _read_message(process)
                if message is None:
                    messages.put(None)
                    return
                messages.put(message)
        except Exception:  # noqa: BLE001 - worker must convert all failures into a bounded response
            messages.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.perf_counter() + _max_runtime()

    def response(request_id: int) -> dict[str, Any]:
        while time.perf_counter() < deadline:
            try:
                message = messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if message and message.get("id") == request_id:
                if message.get("error"):
                    raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
                result = message.get("result")
                return result if isinstance(result, dict) else {"result": result}
        raise TimeoutError("MCP Worker request timed out")

    try:
        _write(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "Jaycode MCP Worker", "version": "1.0.0"}}})
        response(1)
        _write(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _write(process, {"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
        return response(2)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)


def main() -> int:
    try:
        request = json.loads(sys.stdin.readline())
        result = _serve(request["server"], str(request["method"]), request.get("params") or {})
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - worker boundary must never leak a traceback
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
