"""Backend environment (secrets, providers, database, origins). Never exposed to the browser."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class AppEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    APP_PROVIDER_MODE: Literal["live", "demo"] = "live"
    OPENAI_API_KEY: SecretStr | None = None
    TYPESAFE_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-6.1-sol"
    OPENAI_RESEARCH_MODEL: str = "gpt-6.1-sol"
    JEV_MODEL: str = "jev-1.13.0"
    OPENAI_REASONING_EFFORT: str | None = None
    DATABASE_URL: str = (
        "postgresql+asyncpg://perspective:local_development_only@db:5432/perspective"
    )
    APP_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    APP_PUBLIC_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    MAX_SESSION_USD: float | None = None
    HANDOFF_DIR: Path = REPO_ROOT / "handoff"
    STATIC_DIR: Path = REPO_ROOT / "frontend" / "dist"

    @field_validator(
        "OPENAI_API_KEY",
        "TYPESAFE_API_KEY",
        "OPENAI_REASONING_EFFORT",
        "MAX_SESSION_USD",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.APP_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def openai_configured(self) -> bool:
        return self.OPENAI_API_KEY is not None

    @property
    def jev_configured(self) -> bool:
        return self.TYPESAFE_API_KEY is not None


@lru_cache
def get_env() -> AppEnv:
    return AppEnv()
