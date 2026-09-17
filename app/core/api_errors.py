"""Stable, non-sensitive API error envelopes used during the P2 compatibility window."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.observability import metrics


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or "unknown"


def _code_for_status(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "AUTHENTICATION_REQUIRED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_FAILED",
        429: "RATE_LIMITED",
        501: "NOT_IMPLEMENTED",
        503: "DEPENDENCY_UNAVAILABLE",
    }.get(status_code, "INTERNAL_ERROR")


def _envelope(*, status_code: int, error_code: str, message: str, request_id: str, details: dict[str, Any] | None = None, detail: Any = None) -> JSONResponse:
    metrics.inc("jaycode_api_errors_total", labels={"error_code": error_code, "status": str(status_code)})
    return JSONResponse(
        status_code=status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error_code": error_code,
            "message": message,
            "request_id": request_id,
            "details": details or {},
            # Compatibility field for pre-P2 clients. It intentionally mirrors
            # the old HTTPException detail rather than introducing a new shape.
            "detail": detail if detail is not None else message,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "Request failed.")
        error_code = str(detail.get("error_code") or _code_for_status(exc.status_code))
        details = {key: value for key, value in detail.items() if key not in {"message", "detail", "error_code"}}
    else:
        message = str(detail)
        error_code = _code_for_status(exc.status_code)
        details = {}
    return _envelope(status_code=exc.status_code, error_code=error_code, message=message, request_id=_request_id(request), details=details, detail=detail)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _envelope(
        status_code=422,
        error_code="VALIDATION_FAILED",
        message="Request validation failed.",
        request_id=_request_id(request),
        details={"errors": exc.errors()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Do not send internal exception details to callers; request_id allows safe log correlation.
    return _envelope(status_code=500, error_code="INTERNAL_ERROR", message="Internal server error.", request_id=_request_id(request))
