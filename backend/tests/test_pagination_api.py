"""Tests for bounded list endpoints and their total-count header."""

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.api.pagination import MAX_PAGE_SIZE, TOTAL_COUNT_HEADER
from app.auth.security import create_access_token
from app.core.config import get_settings
from app.repositories.conversation import ConversationRepository
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository


def authenticate(
    client: httpx.AsyncClient,
    user_id: int,
) -> None:
    """Attach an authentication cookie for the supplied user."""
    client.cookies.set(
        get_settings().auth_cookie_name,
        create_access_token(user_id),
    )


def create_admin(session: Session, username: str) -> int:
    """Create an administrator and return its identifier."""
    admin = UserRepository(session).create(
        username=username,
        password_hash="hashed-password",
        is_admin=True,
    )
    return admin.id


@pytest.mark.asyncio
async def test_document_list_returns_a_page_and_the_total_count(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Documents are sliced by limit/offset and counted before pagination."""
    with session_factory() as session:
        admin_id = create_admin(session, "pagination-admin")
        repository = DocumentRepository(session)
        for index in range(3):
            repository.create(
                filename=f"stored-{index}.pdf",
                original_filename=f"Guide {index}.pdf",
                sha256=f"{index}" * 64,
                file_size=10,
                uploader_id=admin_id,
            )
    authenticate(client, admin_id)

    first_page = await client.get("/api/admin/documents", params={"limit": 2})
    second_page = await client.get(
        "/api/admin/documents",
        params={"limit": 2, "offset": 2},
    )
    filtered = await client.get(
        "/api/admin/documents",
        params={"search": "Guide 1", "limit": 2},
    )

    assert first_page.status_code == 200
    assert len(first_page.json()["data"]) == 2
    assert first_page.headers[TOTAL_COUNT_HEADER] == "3"
    assert len(second_page.json()["data"]) == 1
    assert second_page.headers[TOTAL_COUNT_HEADER] == "3"
    assert len(filtered.json()["data"]) == 1
    assert filtered.headers[TOTAL_COUNT_HEADER] == "1"


@pytest.mark.asyncio
async def test_conversation_list_is_paginated_for_the_owner(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Conversation pages keep newest-first order and report the owned total."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="pagination-user",
            password_hash="hashed-password",
        )
        repository = ConversationRepository(session)
        titles = [f"chat {index}" for index in range(3)]
        for title in titles:
            repository.create(user_id=user.id, title=title)
        user_id = user.id
    authenticate(client, user_id)

    response = await client.get(
        "/api/conversations",
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["data"]] == ["chat 1"]
    assert response.headers[TOTAL_COUNT_HEADER] == "3"


@pytest.mark.asyncio
async def test_user_list_is_paginated(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """The administrator user list is bounded and reports the full total."""
    with session_factory() as session:
        admin_id = create_admin(session, "pagination-root")
        repository = UserRepository(session)
        for index in range(2):
            repository.create(
                username=f"member-{index}",
                password_hash="hashed-password",
            )
    authenticate(client, admin_id)

    response = await client.get("/api/admin/users", params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()["data"]) == 2
    assert response.headers[TOTAL_COUNT_HEADER] == "3"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": MAX_PAGE_SIZE + 1},
        {"offset": -1},
        {"limit": "many"},
    ],
)
async def test_list_endpoints_reject_invalid_pagination(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    params: dict[str, object],
) -> None:
    """Out-of-range paging parameters are rejected by the shared contract."""
    with session_factory() as session:
        admin_id = create_admin(session, "pagination-invalid")
    authenticate(client, admin_id)

    response = await client.get("/api/admin/documents", params=params)

    assert response.status_code == 422
    assert response.json() == {
        "status": "error",
        "message": "Request validation failed",
    }
