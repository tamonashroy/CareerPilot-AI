"""Application settings, read from the environment (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: SecretStr
    cors_allowed_origins: str = ""

    worker_poll_interval_seconds: float = Field(default=1.0, gt=0)
    worker_lease_grace_seconds: int = Field(default=30, ge=0)
    worker_reclaim_interval_seconds: float = Field(default=30.0, gt=0)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
