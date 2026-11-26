from contextlib import asynccontextmanager
from pathlib import Path

import secrets

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .api import ROUTERS
from .config import check_production_settings, get_settings
from .services.tenancy import CSRF_COOKIE, SESSION_COOKIE

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT = ("/api/auth/login", "/api/auth/oidc/", "/api/integrations/")


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


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    from .services.jobs import start_thread

    start_thread()  # ANALYSIS_WORKER=thread only; queued jobs survive restarts in the database
    yield


def create_app(static_dir: str | Path | None = None) -> FastAPI:
    settings = get_settings()
    check_production_settings(settings)
    app = FastAPI(title="Graft", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=_lifespan)

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok", "auth_mode": settings.AUTH_MODE, "demo_mode": settings.DEMO_MODE}

    @api.get("/ai/status", tags=["health"])
    def ai_status() -> dict:
        """Model availability, separate from liveness: the app stays up when the model is down."""
        from .ai import client
        return client.status()

    for router in ROUTERS:
        api.include_router(router)
    app.include_router(api)

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        """Double-submit CSRF check for state-changing requests that carry a session cookie. Exempt: sign-in
        endpoints (no session yet) and the relay endpoint (bearer token, no cookie)."""
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/") \
                and not request.url.path.startswith(CSRF_EXEMPT) and SESSION_COOKIE in request.cookies:
            token, header = request.cookies.get(CSRF_COOKIE), request.headers.get("x-csrf-token")
            if not token or not header or not secrets.compare_digest(token, header):
                return JSONResponse({"detail": "CSRF check failed; reload the page and try again"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    dist = Path(static_dir if static_dir is not None else settings.STATIC_DIR)
    if not dist.is_absolute():
        dist = (Path(__file__).resolve().parent.parent / dist)
    if (dist / "index.html").is_file():
        _mount_spa(app, dist)
    return app


app = create_app()
