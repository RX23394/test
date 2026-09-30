"""Tests for administrator user-management endpoints."""

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token, hash_password
from app.core.config import get_settings
from app.repositories.user import UserRepository


def authenticate_user(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    *,
    username: str,
    is_admin: bool,
) -> int:
    """Create a user and authenticate the API client."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username=username,
            password_hash=hash_password("secure-password"),
            is_admin=is_admin,
        )
        user_id = user.id
    client.cookies.set(
        get_settings().auth_cookie_name,
        create_access_token(user_id),
    )
    return user_id


@pytest.mark.asyncio
async def test_admin_creates_and_lists_users(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """An administrator can create accounts in both supported roles."""
    authenticate_user(
        client,
        session_factory,
        username="manager",
        is_admin=True,
    )

    create_response = await client.post(
        "/api/admin/users",
        json={
            "username": "new-admin",
            "password": "initial-password",
            "role": "admin",
        },
    )
    list_response = await client.get("/api/admin/users")

    assert create_response.status_code == 201
    assert create_response.json()["data"]["role"] == "admin"
    assert create_response.json()["data"]["is_active"] is True
    assert {user["username"] for user in list_response.json()["data"]} == {
        "manager",
        "new-admin",
    }


@pytest.mark.asyncio
async def test_admin_updates_status_and_role(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """An administrator can deactivate, restore, and promote another user."""
    authenticate_user(
        client,
        session_factory,
        username="manager",
        is_admin=True,
    )
    user_id = authenticate_user(
        client,
        session_factory,
        username="member",
        is_admin=False,
    )
    authenticate_user(
        client,
        session_factory,
        username="second-manager",
        is_admin=True,
    )

    inactive_response = await client.patch(
        f"/api/admin/users/{user_id}/status",
        json={"is_active": False},
    )
    active_response = await client.patch(
        f"/api/admin/users/{user_id}/status",
        json={"is_active": True},
    )
    role_response = await client.patch(
        f"/api/admin/users/{user_id}/role",
        json={"role": "admin"},
    )

    assert inactive_response.json()["data"]["is_active"] is False
    assert active_response.json()["data"]["is_active"] is True
    assert role_response.json()["data"]["role"] == "admin"


@pytest.mark.asyncio
async def test_standard_user_cannot_access_user_management(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """A standard user receives forbidden responses from management APIs."""
    authenticate_user(
        client,
        session_factory,
        username="member",
        is_admin=False,
    )

    list_response = await client.get("/api/admin/users")
    create_response = await client.post(
        "/api/admin/users",
        json={
            "username": "blocked-user",
            "password": "initial-password",
            "role": "user",
        },
    )

    assert list_response.status_code == 403
    assert create_response.status_code == 403
    assert list_response.json()["message"] == "Administrator access required"
