from app.api.routes._domain import build_domain_router
from app.services.api_service import SecurityService

router = build_domain_router(
    SecurityService,
    "security",
    lambda path: path.startswith("/api/v1/security/"),
)
