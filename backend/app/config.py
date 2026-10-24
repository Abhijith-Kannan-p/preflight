"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    cors_origins: str = "http://localhost:3000"
    public_app_url: str = "http://localhost:3000"

    data_dir: Path = REPO_ROOT / "data"

    @property
    def seed_dir(self) -> Path:
        return self.data_dir / "seed"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
