"""Password hashing and JWT token helpers."""

from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.auth import TokenPayload

password_hasher = PasswordHasher()


class AuthTokenError(Exception):
    """Raised when an access token cannot be validated."""


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def create_access_token(
    subject: int,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token for a user identifier."""
    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload: dict[str, object] = {
        "sub": str(subject),
        "iat": issued_at,
        "exp": expires_at,
        "type": "access",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a signed JWT access token."""
    settings = get_settings()
    try:
        payload = cast(
            dict[str, object],
            jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            ),
        )
        return TokenPayload.model_validate(payload)
    except (jwt.InvalidTokenError, ValidationError) as exc:
        raise AuthTokenError("Invalid access token") from exc
