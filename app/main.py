import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as project_router
from app.core.api_errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.config import settings
from app.core.llm_monitor import llm_monitor
from app.core.observability import configure_json_logging, metrics
from app.core.security import security_middleware, validate_security_configuration
from app.harness.supervisor import worker_supervisor
from app.persistence.factory import get_persistence_stores

logger = logging.getLogger("jaycode.api")

# 创建 FastAPI 应用
# 挂载 API 路由
# 如果前端 build 出来了，就把 web/dist 静态资源挂上去

validate_security_configuration()
configure_json_logging()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.middleware("http")(security_middleware)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/ready")
def ready() -> dict[str, object]:
    database_ready = True
    try:
        get_persistence_stores().ping()
    except Exception:  # noqa: BLE001 - readiness must not expose database details
        database_ready = False
    supervisor = worker_supervisor.snapshot()
    worker_ready = not settings.jaycode_worker_supervisor_enabled or bool(supervisor["alive"])
    if not database_ready or not worker_ready:
        raise HTTPException(status_code=503, detail={"database": database_ready, "worker": worker_ready, "supervisor": supervisor})
    return {"status": "ready", "database": database_ready, "worker": worker_ready, "supervisor": supervisor}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> PlainTextResponse:
    tasks = get_persistence_stores().task.list_tasks(limit=1000)
    for status in ("queued", "running", "completed", "failed", "cancelled"):
        metrics.set("jaycode_tasks", sum(task.get("status") == status for task in tasks), {"status": status})
    workers = get_persistence_stores().task.list_workers()
    for status in ("running", "stopped"):
        metrics.set("jaycode_workers_registered", sum(worker.get("status") == status for worker in workers), {"status": status})
    try:
        traces = get_persistence_stores().llm.list_llm_traces(limit=1000)
        llm_monitor.collect(traces)
    except Exception:  # noqa: BLE001 - metrics must not take the API down
        metrics.inc("jaycode_metrics_collection_errors_total")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

# 把它理解成：“把后端接口和前端页面装到同一个壳里”
app.include_router(project_router)


@app.on_event("startup")
def start_runtime_services() -> None:
    get_persistence_stores().ping()
    if settings.jaycode_worker_supervisor_enabled:
        worker_supervisor.max_restarts = max(1, settings.jaycode_worker_supervisor_max_restarts)
        worker_supervisor.worker_count = max(1, settings.jaycode_worker_count)
        worker_supervisor.start()
        if not worker_supervisor.wait_until_ready(settings.jaycode_worker_supervisor_startup_timeout_seconds):
            logger.warning("worker_supervisor_not_ready", extra={"supervisor": worker_supervisor.snapshot()})


@app.on_event("shutdown")
def stop_runtime_services() -> None:
    worker_supervisor.stop()

web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
web_index_file = web_dist / "index.html"
assets_dir = web_dist / "assets"

if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")


@app.get("/", include_in_schema=False)
def web_index() -> FileResponse:
    return FileResponse(web_index_file)
