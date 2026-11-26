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

    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_TIMEOUT_SECONDS: float = 20.0
    LLM_MAX_ATTEMPTS: int = 2

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
    """Outside demo mode the app refuses to start with a guessable session secret."""
    if s.DEMO_MODE:
        return
    if s.SESSION_SECRET == DEV_SESSION_SECRET or len(s.SESSION_SECRET) < 32:
        raise InsecureConfig("SESSION_SECRET must be set to a random value of at least 32 characters "
                             "when DEMO_MODE=false")


@lru_cache
def get_settings() -> Settings:
    return Settings()
