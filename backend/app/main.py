from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .api import ROUTERS
from .config import check_production_settings, get_settings


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA at / with index.html fallback for client-side routes."""
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            candidate = (dist / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index)


def create_app(static_dir: str | Path | None = None) -> FastAPI:
    settings = get_settings()
    check_production_settings(settings)
    app = FastAPI(title="Graft", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok", "auth_mode": settings.AUTH_MODE, "demo_mode": settings.DEMO_MODE}

    for router in ROUTERS:
        api.include_router(router)
    app.include_router(api)

    dist = Path(static_dir if static_dir is not None else settings.STATIC_DIR)
    if not dist.is_absolute():
        dist = (Path(__file__).resolve().parent.parent / dist)
    if (dist / "index.html").is_file():
        _mount_spa(app, dist)
    return app


app = create_app()
