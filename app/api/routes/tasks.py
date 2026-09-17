from app.api.routes._domain import build_domain_router
from app.services.api_service import TaskService

router = build_domain_router(
    TaskService,
    "tasks",
    lambda path: (
        (path == "/api/v1/tasks" or path.startswith("/api/v1/tasks/"))
        and not path.endswith("/learning-plan")
    ) or path in {"/api/v1/agents/collaborate", "/api/v1/workers"},
)
