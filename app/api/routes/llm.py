from app.api.routes._domain import build_domain_router
from app.services.api_service import LlmService

router = build_domain_router(LlmService, "llm", lambda path: path.startswith("/api/v1/llm/"))
