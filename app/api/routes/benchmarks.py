from app.api.routes._domain import build_domain_router
from app.services.api_service import BenchmarkService

router = build_domain_router(
    BenchmarkService,
    "benchmarks",
    lambda path: path.startswith("/api/v1/benchmarks"),
)
