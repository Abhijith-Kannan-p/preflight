"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Real environment variables win; otherwise read the repo-root .env (works from any cwd).
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://preflight:preflight@localhost:5432/preflight"
    jwt_secret: str = "dev-only-secret"

    llm_provider: Literal["gemini", "groq", "none"] = "none"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 8.0

    masking_enabled: bool = True

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    nli_model: str = "cross-encoder/nli-deberta-v3-xsmall"
    skip_model_load: bool = False
    # Generate demo history and precompute the evaluation after boot (off in tests).
    bootstrap_demo: bool = True

    cors_origins: str = "http://localhost:3000"
    public_app_url: str = "http://localhost:3000"

    data_dir: Path = REPO_ROOT / "data"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Accept plain postgres:// URLs (as Neon and Supabase hand them out)."""
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def seed_dir(self) -> Path:
        return self.data_dir / "seed"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
