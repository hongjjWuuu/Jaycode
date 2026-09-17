from app.api.routes._domain import build_domain_router
from app.services.api_service import RagService

router = build_domain_router(
    RagService,
    "rag",
    lambda path: path.startswith(("/api/v1/rag/", "/api/v1/knowledge/", "/api/v1/memories")),
)
