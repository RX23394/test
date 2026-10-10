"""Application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

project_root = Path(__file__).resolve().parents[3]
DEFAULT_JWT_SECRET_KEY = "development-only-change-me-at-least-32-bytes"
PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production", "staging"})
DEVELOPMENT_ENVIRONMENTS = frozenset(
    {"development", "dev", "local", "test", "testing", "ci"}
)
KNOWN_ENVIRONMENTS = PRODUCTION_ENVIRONMENTS | DEVELOPMENT_ENVIRONMENTS


class Settings(BaseSettings):
    """Configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=project_root / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Network RAG"
    app_env: str = "development"
    app_debug: bool = False
    database_url: str = "sqlite:///./network_rag.db"
    document_upload_dir: Path = project_root / "data" / "uploads"
    document_max_upload_bytes: int = 50 * 1024 * 1024
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "document_chunks"
    # Cosine similarity floor for vector candidates. Measured on the bundled
    # multilingual-e5-small model, unrelated Chinese questions score around
    # 0.78 while related ones score above 0.92, so retrieval without a floor
    # always filled the prompt with eight irrelevant chunks.
    retrieval_min_score: float = Field(default=0.87, ge=0.0, le=1.0)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = "not-required"
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60.0
    frontend_origin: str = "http://127.0.0.1:5173"
    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    auth_cookie_name: str = "network_rag_access_token"
    auth_cookie_secure: bool = False
    # Follow-up questions such as "那它的缺点呢？" carry no retrievable terms, so the
    # most recent user turns are prepended to the embedding query, and the newest
    # turns are replayed to the model within a token budget.
    chat_history_turns: int = Field(default=3, ge=0, le=20)
    chat_history_max_tokens: int = Field(default=512, ge=0)

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Reject unsafe authentication defaults in production."""
        environment = self.app_env.strip().lower()
        if environment not in KNOWN_ENVIRONMENTS:
            raise ValueError(
                f"APP_ENV={self.app_env!r} is not recognised; use one of "
                f"{', '.join(sorted(KNOWN_ENVIRONMENTS))}"
            )
        if environment not in PRODUCTION_ENVIRONMENTS:
            return self
        if (
            self.jwt_secret_key == DEFAULT_JWT_SECRET_KEY
            or len(self.jwt_secret_key.encode("utf-8")) < 32
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a non-default value of at least 32 bytes "
                "in production"
            )
        if not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if self.app_debug:
            raise ValueError("APP_DEBUG must be false in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
