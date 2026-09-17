from app.api.routes._domain import build_domain_router
from app.services.api_service import LearningService

router = build_domain_router(
    LearningService,
    "learning",
    lambda path: path.startswith("/api/v1/learning/") or path.endswith("/learning-plan"),
)
