from app.api.routes._domain import build_domain_router
from app.services.api_service import SkillService

router = build_domain_router(SkillService, "skills", lambda path: path.startswith("/api/v1/skills"))
