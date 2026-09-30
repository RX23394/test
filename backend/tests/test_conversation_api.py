"""Tests for authenticated conversation API endpoints."""

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import hash_password
from app.models.message import MessageRole
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.services.conversation import ConversationService


async def authenticate(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> int:
    """Create and authenticate one conversation owner."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="conversation-owner",
            password_hash=hash_password("secure-password"),
        )
        user_id = user.id
    response = await client.post(
        "/api/auth/login",
        json={"username": "conversation-owner", "password": "secure-password"},
    )
    assert response.status_code == 200
    return user_id


@pytest.mark.asyncio
async def test_conversation_crud_and_message_loading(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Create, list, rename, load messages, and delete an owned conversation."""
    user_id = await authenticate(client, session_factory)

    create_response = await client.post(
        "/api/conversations",
        json={"title": "Routing"},
    )
    assert create_response.status_code == 200
    conversation_id = create_response.json()["data"]["id"]

    with session_factory() as session:
        ConversationService(ConversationRepository(session)).add_message(
            conversation_id,
            user_id,
            MessageRole.USER,
            "What is OSPF?",
        )

    list_response = await client.get("/api/conversations")
    assert [item["id"] for item in list_response.json()["data"]] == [conversation_id]

    rename_response = await client.patch(
        f"/api/conversations/{conversation_id}",
        json={"title": "OSPF Notes"},
    )
    assert rename_response.json()["data"]["title"] == "OSPF Notes"

    detail_response = await client.get(f"/api/conversations/{conversation_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["messages"][0]["content"] == "What is OSPF?"

    delete_response = await client.delete(f"/api/conversations/{conversation_id}")
    assert delete_response.json() == {
        "status": "ok",
        "data": True,
        "message": None,
    }
    assert (await client.get("/api/conversations")).json()["data"] == []


@pytest.mark.asyncio
async def test_conversation_endpoints_require_authentication(
    client: httpx.AsyncClient,
) -> None:
    """Conversation data is unavailable without the authentication cookie."""
    response = await client.get("/api/conversations")
    assert response.status_code == 401
