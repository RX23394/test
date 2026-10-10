"""Tests for environment-specific application configuration."""

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_JWT_SECRET_KEY, Settings


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
