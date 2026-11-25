from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TERMSCHECK_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://termscheck:termscheck@localhost:5432/termscheck"
    migration_database_url: str | None = None  # owner role for Alembic; defaults to database_url
    storage_dir: str = "storage"
    extraction_model: str = "claude-sonnet-5-5"
    extraction_max_tokens: int = 16000
    extraction_max_pages: int = 60          # page budget sent to the model after prefiltering
    extraction_server_fallback: bool = True  # server-side refusal fallback (beta)
    # Worst case per extraction = (retries + 1) x timeout; keep it under the nginx proxy_read_timeout (900 s).
    extraction_timeout_s: float = 240.0
    extraction_max_retries: int = 2
    # Upload limits (enforced in the API, not only by the nginx proxy)
    max_pdf_bytes: int = 50 * 1024 * 1024
    max_data_bytes: int = 20 * 1024 * 1024     # CSV / disclosure files
    max_pdf_pages: int = 1500
    ocr_min_chars_per_page: int = 40          # below this median, a PDF is treated as scanned (no text layer)
    llm_mode: str = "anthropic"             # anthropic | recorded (demo without an API key)
    recorded_dir: str = "../data/recorded_extractions"
    cors_origins: str = "http://localhost:5173,http://localhost:18080"


settings = Settings()
