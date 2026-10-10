"""Tests for authentication API endpoints."""

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.auth import LOGIN_RATE_LIMIT_MESSAGE
from app.auth.security import hash_password
from app.core.rate_limit import FixedWindowRateLimiter, get_login_rate_limiter
from app.main import app
from app.models.user import User
from app.repositories.user import UserRepository


def create_user(
    session_factory: sessionmaker[Session],
    *,
    username: str = "alice",
    password: str = "secure-password",
    is_active: bool = True,
) -> User:
    """Create a user through the repository for an authentication test."""
    with session_factory() as session:
        return UserRepository(session).create(
            username=username,
            password_hash=hash_password(password),
            is_active=is_active,
        )


@pytest.mark.asyncio
async def test_login_success_sets_protected_cookie(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Valid credentials return user data and an HttpOnly SameSite cookie."""
    user = create_user(session_factory)

    response = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secure-password"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["data"]["id"] == user.id
    assert response.json()["data"]["username"] == "alice"
    assert "token" not in response.json()
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["data"]["username"] == "alice"


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["alice", "missing-user"])
async def test_login_failure_rejects_invalid_credentials(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    username: str,
) -> None:
    """Invalid credentials return the same unauthorized response."""
    create_user(session_factory)

    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "status": "error",
        "message": "Invalid username or password",
    }


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """An inactive user cannot obtain an authentication cookie."""
    create_user(session_factory, is_active=False)

    response = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secure-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_repeated_failed_logins_are_rate_limited(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Password guessing is bounded and answered with a Retry-After header."""
    create_user(session_factory)
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    responses = [
        await client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        for _ in range(4)
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 429]
    assert responses[-1].json() == {
        "status": "error",
        "message": LOGIN_RATE_LIMIT_MESSAGE,
    }
    assert int(responses[-1].headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_successful_login_clears_failed_attempts(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """A correct password resets the counter instead of keeping the lockout."""
    create_user(session_factory)
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    failed = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    success = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secure-password"},
    )
    after_success = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )

    assert failed.status_code == 401
    assert success.status_code == 200
    assert after_success.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_authentication(client: httpx.AsyncClient) -> None:
    """The current-user endpoint rejects requests without a cookie."""
    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "status": "error",
        "message": "Authentication required",
    }


@pytest.mark.asyncio
async def test_logout_clears_authentication(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Logout expires the cookie and removes access to protected endpoints."""
    create_user(session_factory)
    await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secure-password"},
    )

    logout_response = await client.post("/api/auth/logout")
    me_response = await client.get("/api/auth/me")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "ok"}
    assert me_response.status_code == 401
