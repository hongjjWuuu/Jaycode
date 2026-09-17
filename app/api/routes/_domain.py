"""Small factory used by domain Router modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.api.routing import domain_router
from app.services.api_service import DomainService
from app.services.legacy_handlers import router as legacy_router

ServiceType = TypeVar("ServiceType", bound=DomainService)


def build_domain_router(
    service_type: type[ServiceType],
    name: str,
    owns_path: Callable[[str], bool],
) -> APIRouter:
    handlers = {
        route.endpoint.__name__: route.endpoint
        for route in legacy_router.routes
        if isinstance(route, APIRoute) and owns_path(route.path)
    }
    return domain_router(service_type(name, handlers), owns_path)
