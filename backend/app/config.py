from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_SESSION_SECRET = "dev-only-insecure-session-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite:///./graft.db"
    AUTH_MODE: Literal["demo", "oidc"] = "demo"
    DEMO_MODE: bool = True
    AS_OF_DATE: date = date(2026, 10, 14)
    SESSION_SECRET: str = DEV_SESSION_SECRET
    # Shared password of the fictional demo accounts (AUTH_MODE=demo only). Not a real credential: it is shown on the
    # demo sign-in page. Override it per deployment if you want the demo closed to the public.
    DEMO_PASSWORD: str = "graft-demo"
    # Load data/showcase.json into the demo org after the starter pack (demo mode only; once per database).
    SEED_SHOWCASE: bool = True

    # Private inference (Ollama). Endpoint and model are server configuration only; see docs/deployment.md.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_ALLOWED_HOSTS: str = "127.0.0.1,localhost,::1,ollama"
    # Bearer token for a model server reached through the authenticating gateway (python -m app.gateway), e.g. over a
    # tunnel. Sent only over https, or http to loopback. Empty for a model on the same private network.
    OLLAMA_API_KEY: str = ""
    LLM_MODEL: str = "qwen3:8b"
    LLM_ALLOWED_MODELS: str = "qwen3:8b,gpt-oss:20b"
    # Optional pin: if set, the installed model's digest must match or the model is treated as misconfigured.
    LLM_MODEL_DIGEST: str = ""
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_MAX_ATTEMPTS: int = 2
    LLM_CONTEXT_TOKENS: int = 16384
    LLM_MAX_CONCURRENCY: int = 1
    LLM_QUEUE_WAIT_SECONDS: float = 5.0
    # "false" disables model thinking (qwen3); gpt-oss accepts "low" | "medium" | "high"; "default" sends nothing.
    LLM_THINK: str = "false"
    AGENT_MAX_SECONDS: int = 180
    # Store raw model responses on analysis runs (debugging only; off in normal operation).
    AI_DEBUG_CAPTURE: bool = False
    # Background analysis: thread (in the web process) | external (python -m app.worker) | inline (tests, CLI)
    ANALYSIS_WORKER: Literal["thread", "external", "inline"] = "thread"
    # Inbound relay payload limit (bytes of the JSON request).
    INBOUND_MAX_BYTES: int = 65536

    # Sessions and OIDC (production identity). Secrets come from the environment only.
    SESSION_HOURS: float = 8.0
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""
    OIDC_SCOPES: str = "openid email profile"
    OIDC_ALGORITHMS: str = "RS256,ES256,PS256"
    # Tenant this identity provider signs people into, and optional group -> role provisioning, e.g.
    # {"graft-pmo": "pmo_coordinator", "graft-tech-leads": "technical_owner"}
    OIDC_ORG_SLUG: str = ""
    OIDC_GROUPS_CLAIM: str = "groups"
    OIDC_GROUP_ROLE_MAP: str = ""

    # Built SPA directory; served at / when it exists.
    STATIC_DIR: str = "../frontend/dist"

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise provider URLs (Render gives postgres://) to the psycopg3 driver."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


class InsecureConfig(RuntimeError):
    pass


def check_production_settings(s: "Settings") -> None:
    """Fail closed. Outside demo mode: OIDC only, a strong session secret and complete identity settings.
    With AUTH_MODE=oidc (any mode): the issuer, client id and redirect URI must be set."""
    if s.AUTH_MODE == "oidc":
        missing = [k for k in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_REDIRECT_URI", "OIDC_ORG_SLUG")
                   if not getattr(s, k)]
        if missing:
            raise InsecureConfig("AUTH_MODE=oidc requires " + ", ".join(missing))
        for k in ("OIDC_ISSUER", "OIDC_REDIRECT_URI"):
            v = getattr(s, k)
            if not (v.startswith("https://") or v.startswith("http://localhost") or v.startswith("http://127.0.0.1")):
                raise InsecureConfig(f"{k} must use https (http only for localhost)")
    if s.DEMO_MODE:
        return
    if s.AUTH_MODE != "oidc":
        raise InsecureConfig("DEMO_MODE=false requires AUTH_MODE=oidc (demo accounts are disabled in production)")
    if s.SESSION_SECRET == DEV_SESSION_SECRET or len(s.SESSION_SECRET) < 32:
        raise InsecureConfig("SESSION_SECRET must be set to a random value of at least 32 characters "
                             "when DEMO_MODE=false")


@lru_cache
def get_settings() -> Settings:
    return Settings()
