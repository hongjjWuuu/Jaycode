from app.api.routes._domain import build_domain_router
from app.services.api_service import MarketplaceService

router = build_domain_router(
    MarketplaceService,
    "marketplace",
    lambda path: path.startswith("/api/v1/marketplace/"),
)
