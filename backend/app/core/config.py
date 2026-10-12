"""Application settings."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Return the repository root, which is three levels above this module."""
    return Path(__file__).resolve().parents[3]


REPOSITORY_ROOT = _project_root()
# Local SQLite and upload paths live beside the application in ``backend/`` --
# that is where the documented launch (``cd backend``) puts them. Resolving them
# explicitly keeps one database regardless of the directory the server is
# started from; a relative path left to the process working directory silently
# selects a different, empty database.
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
SQLITE_URL_PREFIX = "sqlite:///"
# A relative SQLite path is written as ``sqlite:///./name.db``; the leading dot
# would otherwise be taken for the root of an absolute POSIX path.
SQLITE_URL_PATTERN = re.compile(r"^sqlite:///\.{1,2}/(?P<path>.+)$")
DEFAULT_JWT_SECRET_KEY = "development-only-change-me-at-least-32-bytes"
# Browsers treat "localhost" and "127.0.0.1" as different origins, and Vite
# prints a localhost URL by default, so a dev frontend is reached under either
# spelling. Both are loopback names for the same machine, so accepting the
# equivalents of the configured frontend origin is not a widening of trust.
LOOPBACK_HOST_ALIASES = {
    "127.0.0.1": ("localhost", "::1"),
    "localhost": ("127.0.0.1", "::1"),
    "::1": ("127.0.0.1", "localhost"),
}
PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production", "staging"})
DEVELOPMENT_ENVIRONMENTS = frozenset(
    {"development", "dev", "local", "test", "testing", "ci"}
)
KNOWN_ENVIRONMENTS = PRODUCTION_ENVIRONMENTS | DEVELOPMENT_ENVIRONMENTS


class Settings(BaseSettings):
    """Configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Network RAG"
    app_env: str = "development"
    app_debug: bool = False
    database_url: str = "sqlite:///./network_rag.db"
    document_upload_dir: Path = REPOSITORY_ROOT / "data" / "uploads"
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
    # A grounded answer has to be reproducible, so sampling is disabled and the
    # completion is capped instead of letting the model expand indefinitely.
    openai_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    openai_max_tokens: int = Field(default=1024, ge=1)
    # The encoder is a local model, so a cached copy is all it needs. Left on, the
    # process never asks huggingface.co whether the cache is current -- a machine
    # that cannot reach the Hub otherwise spends about a minute in retries before
    # every first answer. A missing cache then fails loudly instead of silently
    # degrading, which is why this is not switched off automatically.
    embedding_offline: bool = True
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
    # An indexing job that stopped without finalizing its status keeps the
    # document in "processing" forever; after this lease it can be retried.
    indexing_lease_seconds: int = Field(default=900, ge=60)
    # In-process request limits: password guessing and chat request floods are
    # bounded per client address and per user. A multi-worker deployment needs a
    # shared store or a gateway instead (see README).
    login_max_attempts: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=300, ge=1)
    chat_max_requests: int = Field(default=30, ge=1)
    chat_window_seconds: int = Field(default=60, ge=1)

    @field_validator("database_url")
    @classmethod
    def resolve_relative_sqlite_path(cls, value: str) -> str:
        """Anchor a relative SQLite path to the backend directory.

        ``sqlite:///./network_rag.db`` means "the database beside the
        application", so it is resolved against ``backend/`` instead of the
        process working directory. Absolute paths
        (``sqlite:////app/data/network_rag.db``) and in-memory URLs are left
        exactly as supplied.
        """
        match = SQLITE_URL_PATTERN.match(value)
        if match is None:
            return value
        # POSIX-style absolute form, which SQLAlchemy also reads correctly on
        # Windows (``sqlite:///F:/dir/file.db`` -> ``F:/dir/file.db``).
        resolved = (BACKEND_ROOT / match.group("path")).resolve().as_posix()
        return f"{SQLITE_URL_PREFIX}{resolved}"

    @property
    def cors_allow_origins(self) -> list[str]:
        """Return the browser origins allowed to call the API.

        The configured origin comes first; when it is a loopback address its
        equivalent spellings are allowed too. That keeps the browser's CORS
        check aligned with what ``scripts.dev`` and ``start-dev.bat`` actually
        serve, which auto-select the frontend host separately from this value.
        """
        origin = self.frontend_origin.strip().rstrip("/")
        parsed = urlsplit(origin)
        host = parsed.hostname or ""
        # Keep the scheme and port, swap only the hostname for its equivalent
        # spelling. An IPv6 literal needs its brackets back in the Origin form.
        prefix = f"{parsed.scheme}://"
        suffix = f":{parsed.port}" if parsed.port is not None else ""
        candidates = [origin]
        candidates.extend(
            f"{prefix}{f'[{alias}]' if ':' in alias else alias}{suffix}"
            for alias in LOOPBACK_HOST_ALIASES.get(host, ())
            if alias != host
        )
        return list(dict.fromkeys(candidates))

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
