"""Public API aggregation; domain modules own the HTTP routing surface."""

from fastapi import APIRouter

from app.api.routes import (
    benchmarks,
    learning,
    llm,
    marketplace,
    mcp,
    projects,
    rag,
    security,
    skills,
    tasks,
    workflows,
)
from app.api.routing import legacy_api_paths

router = APIRouter(prefix="/api/v1", tags=["Jaycode"])

_domain_routers = (
    projects.router,
    tasks.router,
    workflows.router,
    rag.router,
    learning.router,
    skills.router,
    marketplace.router,
    mcp.router,
    benchmarks.router,
    llm.router,
    security.router,
)
_registered_paths = {
    f"/api/v1{route.path}"
    for _domain_router in _domain_routers
    for route in _domain_router.routes
    if hasattr(route, "path")
}
_missing_paths = legacy_api_paths() - _registered_paths
if _missing_paths:
    raise RuntimeError(f"P2-1 routing split omitted legacy paths: {sorted(_missing_paths)}")

for _domain_router in _domain_routers:
    router.include_router(_domain_router)
