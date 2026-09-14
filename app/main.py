from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as project_router
from app.core.config import settings
from app.core.security import security_middleware

# 创建 FastAPI 应用
# 挂载 API 路由
# 如果前端 build 出来了，就把 web/dist 静态资源挂上去

app = FastAPI(title=settings.app_name, version="0.1.0")
app.middleware("http")(security_middleware)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

# 把它理解成：“把后端接口和前端页面装到同一个壳里”
app.include_router(project_router)

web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
web_index_file = web_dist / "index.html"
assets_dir = web_dist / "assets"

if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")


@app.get("/", include_in_schema=False)
def web_index() -> FileResponse:
    return FileResponse(web_index_file)
