from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite:///./dais.db"
    AUTH_MODE: Literal["demo", "oidc"] = "demo"
    DEMO_MODE: bool = True
    AS_OF_DATE: date = date(2026, 10, 14)
    SESSION_SECRET: str = "dev-only-change-me"

    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-5-5"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
