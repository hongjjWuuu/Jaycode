"""Compatibility-preserving registration of legacy operations by API domain."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.services.api_service import DomainService
from app.services.legacy_handlers import router as legacy_router


def domain_router(
    service: DomainService,
    owns_path: Callable[[str], bool],
) -> APIRouter:
    """Expose one domain's existing operations through its service boundary.

    APIRoute metadata is copied verbatim so generated OpenAPI and externally
    observable endpoint contracts stay stable during the structural split.
    """
    router = APIRouter()
    for route in legacy_router.routes:
        if not isinstance(route, APIRoute) or not owns_path(route.path):
            continue
        router.add_api_route(
            _relative_path(route.path),
            _service_endpoint(service, route.endpoint),
            methods=route.methods,
            response_model=route.response_model,
            status_code=route.status_code,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            name=route.name,
            tags=route.tags,
            include_in_schema=route.include_in_schema,
            operation_id=route.operation_id,
        )
    return router


def legacy_api_paths() -> set[str]:
    return {route.path for route in legacy_router.routes if isinstance(route, APIRoute)}


def _relative_path(path: str) -> str:
    prefix = "/api/v1"
    if not path.startswith(prefix):
        raise RuntimeError(f"Legacy route is outside {prefix}: {path}")
    relative = path.removeprefix(prefix)
    return relative or "/"


def _service_endpoint(service: DomainService, endpoint: Callable[..., Any]) -> Callable[..., Any]:
    operation = endpoint.__name__
    if inspect.iscoroutinefunction(endpoint):

        @wraps(endpoint)
        async def invoke_async(*args: Any, **kwargs: Any) -> Any:
            return await service.invoke(operation, *args, **kwargs)

        return invoke_async

    @wraps(endpoint)
    def invoke_sync(*args: Any, **kwargs: Any) -> Any:
        return service.invoke(operation, *args, **kwargs)

    return invoke_sync
