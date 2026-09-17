from app.api.routes._domain import build_domain_router
from app.services.api_service import WorkflowService

router = build_domain_router(WorkflowService, "workflows", lambda path: path.startswith("/api/v1/workflows"))
