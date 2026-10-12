"""Tests for environment-specific application configuration."""

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, DEFAULT_JWT_SECRET_KEY, Settings


def test_development_allows_local_authentication_defaults() -> None:
    """Development settings remain usable over local HTTP."""
    settings = Settings(
        _env_file=None,
        app_env="development",
        jwt_secret_key=DEFAULT_JWT_SECRET_KEY,
        auth_cookie_secure=False,
    )

    assert settings.auth_cookie_secure is False


def test_production_rejects_default_jwt_secret() -> None:
    """Production cannot start with the published development secret."""
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key=DEFAULT_JWT_SECRET_KEY,
            auth_cookie_secure=True,
        )


def test_production_rejects_short_jwt_secret() -> None:
    """Production requires at least 32 bytes of JWT key material."""
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(
            _env_file=None,
            app_env="prod",
            jwt_secret_key="too-short",
            auth_cookie_secure=True,
        )


def test_production_requires_secure_authentication_cookie() -> None:
    """Production authentication cookies must be restricted to HTTPS."""
    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="a-secure-production-secret-of-32-bytes",
            auth_cookie_secure=False,
        )


def test_production_rejects_debug_mode() -> None:
    """Production cannot expose debug tracebacks to API clients."""
    with pytest.raises(ValidationError, match="APP_DEBUG"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="a-secure-production-secret-of-32-bytes",
            auth_cookie_secure=True,
            app_debug=True,
        )


def test_unknown_environment_name_is_rejected() -> None:
    """A misspelled APP_ENV must not silently disable production checks."""
    with pytest.raises(ValidationError, match="APP_ENV"):
        Settings(
            _env_file=None,
            app_env="produciton",
            jwt_secret_key=DEFAULT_JWT_SECRET_KEY,
            auth_cookie_secure=False,
        )


def test_staging_is_treated_as_a_production_like_environment() -> None:
    """Staging deployments get the same hardening as production."""
    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings(
            _env_file=None,
            app_env="staging",
            jwt_secret_key="a-secure-production-secret-of-32-bytes",
            auth_cookie_secure=False,
        )


def test_production_accepts_hardened_authentication_settings() -> None:
    """Production accepts a custom key together with a secure cookie."""
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="a-secure-production-secret-of-32-bytes",
        auth_cookie_secure=True,
    )

    assert settings.app_env == "production"


def test_cors_origins_include_every_loopback_spelling() -> None:
    """Both loopback names of the dev frontend are accepted as origins.

    The browser treats ``localhost`` and ``127.0.0.1`` as distinct origins, so a
    single-entry allow-list rejects the frontend whenever it is opened under the
    other spelling -- which surfaces as "Failed to fetch" rather than a readable
    error. The configured origin stays first so it remains the primary value.
    """
    settings = Settings(
        _env_file=None,
        frontend_origin="http://127.0.0.1:5173",
    )

    assert settings.cors_allow_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://[::1]:5173",
    ]


def test_cors_origins_keep_a_non_loopback_origin_alone() -> None:
    """A real host is trusted exactly as configured, with no aliases added."""
    settings = Settings(
        _env_file=None,
        frontend_origin="https://rag.example.com",
    )

    assert settings.cors_allow_origins == ["https://rag.example.com"]


def test_cors_origins_accept_the_ipv6_loopback_spelling() -> None:
    """A configured IPv6 loopback origin resolves to its equivalents."""
    settings = Settings(
        _env_file=None,
        frontend_origin="http://[::1]:5173",
    )

    assert settings.cors_allow_origins == [
        "http://[::1]:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]


def test_relative_sqlite_path_is_anchored_to_the_backend_directory() -> None:
    """The local database does not depend on the working directory.

    Left relative, ``sqlite:///./network_rag.db`` resolves against the process
    working directory, so starting the server from the repository root instead
    of ``backend/`` silently opens a different, empty database and every query
    fails with "no such table".
    """
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///./network_rag.db",
    )

    assert settings.database_url == (
        f"sqlite:///{(BACKEND_ROOT / 'network_rag.db').as_posix()}"
    )


def test_absolute_sqlite_path_is_left_untouched() -> None:
    """A container path must not be rewritten to a host path."""
    settings = Settings(
        _env_file=None,
        database_url="sqlite:////app/data/network_rag.db",
    )

    assert settings.database_url == "sqlite:////app/data/network_rag.db"


def test_in_memory_sqlite_url_is_left_untouched() -> None:
    """An in-memory database has no path to anchor."""
    settings = Settings(_env_file=None, database_url="sqlite://")

    assert settings.database_url == "sqlite://"
