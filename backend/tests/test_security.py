"""Tests for password and JWT security helpers."""

from datetime import timedelta

import pytest

from app.auth.security import (
    AuthTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    """Passwords are stored as Argon2id hashes and verify correctly."""
    password = "correct-horse-battery-staple"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_jwt_round_trip() -> None:
    """A signed access token preserves its user subject and token type."""
    token = create_access_token(42, expires_delta=timedelta(minutes=5))

    payload = decode_access_token(token)

    assert payload.sub == "42"
    assert payload.type == "access"


def test_expired_jwt_is_rejected() -> None:
    """An expired access token cannot be decoded as valid credentials."""
    token = create_access_token(42, expires_delta=timedelta(seconds=-1))

    with pytest.raises(AuthTokenError):
        decode_access_token(token)


def test_tampered_jwt_is_rejected() -> None:
    """A token with a modified signature cannot be decoded."""
    token = create_access_token(42)
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered_token = f"{header}.{payload}.{replacement}{signature[1:]}"

    with pytest.raises(AuthTokenError):
        decode_access_token(tampered_token)
