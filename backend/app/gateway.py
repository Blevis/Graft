"""Authenticating gateway in front of a local Ollama, for exposing it through a tunnel (e.g. to the Render demo).

Ollama has no authentication of its own. This gateway is the only thing the tunnel points at. It:
- requires `Authorization: Bearer <GATEWAY_TOKEN>` (constant-time compare) on every request;
- forwards only what Graft uses: GET /api/tags, GET /api/version and non-streaming POST /api/chat;
- accepts chat requests only for models on LLM_ALLOWED_MODELS and refuses cloud models;
- caps request size and the request rate.

Run on the machine that runs Ollama:
    python -m app.gateway --port 11435            # prints a fresh token unless GATEWAY_TOKEN is set
    cloudflared tunnel --url http://127.0.0.1:11435
Then on Render: OLLAMA_BASE_URL=https://<tunnel host>, OLLAMA_ALLOWED_HOSTS=<tunnel host>, OLLAMA_API_KEY=<token>.
Use fictional data only over a tunnel; real employee data belongs on the private deployment (docs/deployment.md)."""
import argparse
import json
import os
import secrets
import threading
import time
from collections import deque

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .ai.client import CLOUD_MARKERS
from .config import get_settings

MAX_BODY = 512 * 1024
RATE_PER_MINUTE = 30
UPSTREAM_TIMEOUT = 300.0


def create_gateway(token: str, upstream: str = "http://127.0.0.1:11434",
                   transport: httpx.BaseTransport | None = None) -> FastAPI:
    if len(token) < 24:
        raise ValueError("GATEWAY_TOKEN must be at least 24 characters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed = {m.strip() for m in get_settings().LLM_ALLOWED_MODELS.split(",") if m.strip()}
    recent: deque[float] = deque()
    lock = threading.Lock()
    expected = f"Bearer {token}".encode()

    def deny(status: int, detail: str) -> JSONResponse:
        return JSONResponse({"error": detail}, status_code=status)

    def rate_ok() -> bool:
        now = time.monotonic()
        with lock:
            while recent and now - recent[0] > 60:
                recent.popleft()
            if len(recent) >= RATE_PER_MINUTE:
                return False
            recent.append(now)
            return True

    def forward(method: str, path: str, body: bytes | None = None) -> Response:
        try:
            with httpx.Client(base_url=upstream, timeout=UPSTREAM_TIMEOUT, trust_env=False, transport=transport) as h:
                r = h.request(method, path, content=body, headers={"Content-Type": "application/json"} if body else None)
        except httpx.HTTPError:
            return deny(502, "Ollama is not reachable from the gateway")
        return Response(r.content, status_code=r.status_code, media_type="application/json")

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        given = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(given, expected):
            return deny(401, "unauthorized")
        if not rate_ok():
            return deny(429, "rate limit")
        return await call_next(request)

    @app.get("/api/tags")
    def tags():
        return forward("GET", "/api/tags")

    @app.get("/api/version")
    def version():
        return forward("GET", "/api/version")

    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.body()
        if len(body) > MAX_BODY:
            return deny(413, "request too large")
        try:
            payload = json.loads(body)
        except ValueError:
            return deny(400, "invalid JSON")
        model = str(payload.get("model", ""))
        if model not in allowed or any(m in model.lower() for m in CLOUD_MARKERS):
            return deny(403, f"model '{model}' is not allowed")
        if payload.get("stream", True) is not False:
            return deny(400, "only stream=false is accepted")
        return forward("POST", "/api/chat", body)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"])
    def everything_else(path: str):
        return deny(404, "not found")  # pull, push, delete, create, generate, embeddings... never exposed

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=11435)
    ap.add_argument("--upstream", default="http://127.0.0.1:11434", help="local Ollama address")
    args = ap.parse_args()
    token = os.environ.get("GATEWAY_TOKEN") or secrets.token_urlsafe(32)
    if not os.environ.get("GATEWAY_TOKEN"):
        print(f"GATEWAY_TOKEN (set this as OLLAMA_API_KEY on Render): {token}", flush=True)
    # Loopback only: the tunnel client connects locally; nothing else on the network can reach the gateway.
    uvicorn.run(create_gateway(token, args.upstream), host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
