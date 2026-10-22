"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://preflight:preflight@localhost:5432/preflight"
    jwt_secret: str = "dev-only-secret"

    llm_provider: Literal["gemini", "groq", "none"] = "none"
    llm_model: str = "gemini-2.0-flash"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 8.0

    masking_enabled: bool = True

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    nli_model: str = "cross-encoder/nli-deberta-v3-xsmall"
    skip_model_load: bool = False

    cors_origins: str = "http://localhost:3000"
    public_app_url: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
