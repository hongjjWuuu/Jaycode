from app.api.routes._domain import build_domain_router
from app.services.api_service import McpService

router = build_domain_router(McpService, "mcp", lambda path: path.startswith("/api/v1/mcp/"))
