from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TERMSCHECK_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://termscheck:termscheck@localhost:5432/termscheck"
    storage_dir: str = "storage"
    extraction_model: str = "claude-sonnet-5-5"
    extraction_max_tokens: int = 16000
    extraction_max_pages: int = 60          # page budget sent to the model after prefiltering
    extraction_server_fallback: bool = True  # server-side refusal fallback (beta)
    cors_origins: str = "http://localhost:5173,http://localhost:8080"


settings = Settings()
