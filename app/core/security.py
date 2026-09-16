from __future__ import annotations

import contextvars
import hashlib
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.observability import metrics
from app.persistence.factory import get_persistence_stores
from app.persistence.postgres_config import validate_matching_postgres_targets


@dataclass(frozen=True)
class AuthContext:
    actor_id: str
    role: str
    request_id: str
    authenticated: bool = False


_request_context: contextvars.ContextVar[AuthContext | None] = contextvars.ContextVar(
    "jaycode_request_context", default=None
)
logger = logging.getLogger("jaycode.api")


def current_auth_context() -> AuthContext | None:
    return _request_context.get()


def execution_auth_context() -> AuthContext:
    """Return the request identity or a clearly-labelled internal identity."""
    context = current_auth_context()
    if context is not None:
        return context
    return AuthContext("system-agent", "system-agent", f"internal_{uuid4().hex}", authenticated=False)


def _configured_keys() -> dict[str, str]:
    result: dict[str, str] = {}
    for item in settings.jaycode_api_keys.split(","):
        raw = item.strip()
        if not raw or ":" not in raw:
            continue
        key, role = raw.rsplit(":", 1)
        if key.strip() and role.strip().lower() in {"user", "reviewer", "admin", "system-agent"}:
            result[key.strip()] = role.strip().lower()
    return result


def _auth_required() -> bool:
    return settings.jaycode_auth_enabled or settings.app_env.lower() in {"prod", "production"}


def validate_security_configuration() -> None:
    """Fail closed before serving traffic with an unusable production auth setup."""
    if settings.app_env.lower() in {"prod", "production"} and not settings.jaycode_auth_enabled:
        raise RuntimeError("Production cannot disable JAYCODE_AUTH_ENABLED")
    if settings.app_env.lower() in {"prod", "production"} and not _configured_keys():
        raise RuntimeError("Production requires JAYCODE_API_KEYS")
    if settings.jaycode_persistence_store.lower() == "postgres" and not settings.database_url:
        raise RuntimeError("JAYCODE_PERSISTENCE_STORE=postgres requires DATABASE_URL")
    if settings.jaycode_persistence_store.lower() == "postgres":
        validate_matching_postgres_targets(settings.database_url, settings.pgvector_database_url)
        raise RuntimeError("PostgreSQL core adapter is not wired to every application domain; refusing mixed SQLite/PostgreSQL persistence.")


def _auth_error(error_code: str, message: str, request_id: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


def _context_from_request(request: Request, request_id: str) -> AuthContext | None:
    if not _auth_required():
        return AuthContext("local-user", "admin", request_id, authenticated=False)
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    for configured_key, role in _configured_keys().items():
        if secrets.compare_digest(token.strip(), configured_key):
            fingerprint = hashlib.sha256(configured_key.encode("utf-8")).hexdigest()[:12]
            return AuthContext(f"api-key:{fingerprint}", role, request_id, authenticated=True)
    return None


def required_role(method: str, path: str) -> str:
    normalized = path.lower()
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return "user"
    if normalized.startswith("/api/v1/tasks/") and any(
        suffix in normalized for suffix in ("/approve", "/reject", "/revise", "/review-action")
    ):
        return "reviewer"
    admin_prefixes = (
        "/api/v1/skills/",
        "/api/v1/marketplace/",
        "/api/v1/mcp/servers",
        "/api/v1/mcp/registered-tools/",
        "/api/v1/mcp/tools/approval",
        "/api/v1/llm/prompts",
        "/api/v1/workflows",
        "/api/v1/security",
    )
    if normalized.startswith(admin_prefixes):
        if normalized.endswith(("/execute", "/allow-check")):
            return "user"
        if normalized.endswith("/preview"):
            return "admin"
        return "admin"
    if normalized in {"/api/v1/mcp/tools/call"}:
        return "user"
    return "user"


def role_allows(actual: str, required: str) -> bool:
    ranks = {"user": 1, "reviewer": 2, "admin": 3, "system-agent": 4}
    return ranks.get(actual, 0) >= ranks.get(required, 99) or actual == "system-agent"


def _action_for_request(method: str, path: str) -> tuple[str, str, str]:
    parts = [part for part in path.split("/") if part]
    resource_type = parts[2] if len(parts) > 2 else "api"
    resource_id = parts[3] if len(parts) > 3 else ""
    return f"{method.upper()} {path}", resource_type, resource_id


def _audit(context: AuthContext, method: str, path: str, status: str, metadata: dict[str, Any] | None = None) -> None:
    action, resource_type, resource_id = _action_for_request(method, path)
    get_persistence_stores().audit.save_security_audit(
        {
            "request_id": context.request_id,
            "actor_id": context.actor_id,
            "role": context.role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "status": status,
            "metadata": metadata or {},
        }
    )


def audit_action(action: str, resource_type: str, resource_id: str = "", status: str = "completed", metadata: dict[str, Any] | None = None) -> None:
    context = execution_auth_context()
    get_persistence_stores().audit.save_security_audit(
        {
            "request_id": context.request_id,
            "actor_id": context.actor_id,
            "role": context.role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "status": status,
            "metadata": metadata or {},
        }
    )


async def security_middleware(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
    if not request.url.path.startswith("/api/v1/") or not _auth_required():
        context = AuthContext("local-user", "admin", request_id, authenticated=False)
        token = _request_context.set(context)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            metrics.inc("jaycode_http_requests_total", labels={"path": request.url.path, "status": str(response.status_code)})
            metrics.observe("jaycode_http_request", started, {"path": request.url.path})
            return response
        finally:
            _request_context.reset(token)

    context = _context_from_request(request, request_id)
    if context is None:
        anonymous = AuthContext("anonymous", "anonymous", request_id)
        _audit(anonymous, request.method, request.url.path, "authentication_failed")
        return _auth_error("AUTHENTICATION_REQUIRED", "Valid API key is required.", request_id, 401)
    required = required_role(request.method, request.url.path)
    if not role_allows(context.role, required):
        _audit(context, request.method, request.url.path, "authorization_failed", {"required_role": required})
        return _auth_error("FORBIDDEN", f"{required} role is required.", request_id, 403)

    token = _request_context.set(context)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        _audit(context, request.method, request.url.path, str(response.status_code), {"required_role": required})
        metrics.inc("jaycode_http_requests_total", labels={"path": request.url.path, "status": str(response.status_code)})
        metrics.observe("jaycode_http_request", started, {"path": request.url.path})
        logger.info("request_completed", extra={"request_id": request_id, "actor_id": context.actor_id, "role": context.role, "status": str(response.status_code), "latency_ms": round((time.perf_counter() - started) * 1000, 2)})
        return response
    finally:
        _request_context.reset(token)
