from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Postgres ---
    postgres_user: str = "focusstream"
    postgres_password: str = "focusstream"
    postgres_db: str = "focusstream"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # --- Redis / Celery ---
    redis_url: str = "redis://redis:6379/0"
    # How often Celery beat polls every active source, in seconds.
    poll_interval_seconds: float = 900.0  # 15 minutes

    # --- Embeddings ---
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-large"
    # Kept <= 2000 so pgvector's HNSW index can be built (see .env.example).
    embedding_dim: int = 1536

    # --- Transcription (Whisper, for podcasts) ---
    transcription_enabled: bool = True
    whisper_model: str = "whisper-1"
    # Per-episode cost/time cap: only the first N minutes are transcribed.
    podcast_max_duration_minutes: int = 120
    # Backlog throttle: on each poll, only the newest N episodes are transcribed;
    # older new episodes are embedded on show-notes only.
    podcast_max_episodes_per_poll: int = 5

    # --- LLM synthesis ---
    anthropic_api_key: str = ""
    synthesis_model: str = "claude-sonnet-5"

    # --- Signal tiers (application-configurable, per product decision) ---
    high_signal_threshold: float = 0.90
    contextual_threshold: float = 0.75
    # Cards scoring below this are archived (not surfaced, not stored).
    min_store_threshold: float = 0.75
    # Only these tiers receive an LLM-generated ai_summary (cost control).
    synthesize_tiers: set[str] = {"high_signal"}

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
