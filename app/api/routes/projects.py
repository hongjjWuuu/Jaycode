from app.api.routes._domain import build_domain_router
from app.services.api_service import ProjectService

router = build_domain_router(
    ProjectService,
    "projects",
    lambda path: path.startswith("/api/v1/projects/") or path == "/api/v1/code/review",
)
