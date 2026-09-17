from __future__ import annotations

from fastapi.routing import APIRoute

from app.api.routes import _domain_routers
from app.services.api_service import DomainService
from app.services.legacy_handlers import router as legacy_router


def _operations(routes: list[object], prefix: str = "") -> set[tuple[str, str]]:
    return {
        (f"{prefix}{route.path}", method)
        for route in routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def test_domain_routers_preserve_every_legacy_api_operation() -> None:
    legacy_operations = _operations(list(legacy_router.routes))
    split_operations = {
        operation
        for router in _domain_routers
        for operation in _operations(list(router.routes), prefix="/api/v1")
    }
    assert split_operations == legacy_operations


def test_domain_service_is_an_explicit_reusable_invocation_boundary() -> None:
    service = DomainService("test", {"double": lambda value: value * 2})
    assert service.invoke("double", 21) == 42
