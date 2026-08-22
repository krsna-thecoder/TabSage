"""TabSage backend configuration — NON-SECRET settings only.

⚠️  BYOK invariant: this module must NEVER load or hold a provider API key.
    The user's key arrives per request via the `X-Provider-Key` header
    (see deps.py) and is used transiently, never persisted or configured here.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Non-secret runtime settings, loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment name: "dev" | "prod"
    env: str = "dev"

    # CORS: comma-separated allowed origins (NEVER "*").
    allowed_origins: str = "http://localhost,http://localhost:8000"

    # Server bind (local dev)
    host: str = "127.0.0.1"
    port: int = 8000

    # Ephemeral session store TTL (seconds)
    session_ttl_seconds: int = 3600

    # Payload / volume caps (Section 10 abuse limits) — enforced in later phases.
    max_text_chars: int = 200_000
    max_chunks_per_ingest: int = 400
    max_sources_per_session: int = 20
    max_question_chars: int = 2_000

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse the comma-separated origins string into a clean list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.env.lower() == "dev"


# Single shared settings instance.
settings = Settings()
