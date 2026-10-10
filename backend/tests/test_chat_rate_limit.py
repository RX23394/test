"""Tests for chat request rate limiting."""

from collections.abc import Sequence

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.chat import CHAT_RATE_LIMIT_MESSAGE
from app.auth.security import create_access_token
from app.core.config import get_settings
from app.core.rate_limit import FixedWindowRateLimiter, get_chat_rate_limiter
from app.main import app
from app.rag.dependencies import get_embedding_service, get_qdrant_repository
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.schemas.search import RetrievalCandidate


class FakeQueryEmbedding:
    """Return one deterministic query vector without loading a model."""

    def embed_query(self, text: str) -> list[list[float]]:
        """Return a single fixed vector for any question."""
        del text
        return [[0.0, 1.0]]


class EmptyVectorRepository:
    """Return no vector candidate, like an empty collection."""

    def search(
        self,
        vector: Sequence[float],
        limit: int,
    ) -> list[RetrievalCandidate]:
        """Return an empty candidate list."""
        del vector, limit
        return []


@pytest.mark.asyncio
async def test_chat_stream_rejects_requests_over_the_user_limit(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """A user flooding the streaming endpoint receives 429 with Retry-After."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="chat-limiter",
            password_hash="hashed-password",
        )
        conversation = ConversationRepository(session).create(user_id=user.id)
        user_id = user.id
        conversation_id = conversation.id
    client.cookies.set(
        get_settings().auth_cookie_name,
        create_access_token(user_id),
    )
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)
    app.dependency_overrides[get_embedding_service] = FakeQueryEmbedding
    app.dependency_overrides[get_qdrant_repository] = EmptyVectorRepository
    app.dependency_overrides[get_chat_rate_limiter] = lambda: limiter

    first = await client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation_id, "message": "What is OSPF?"},
    )
    second = await client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation_id, "message": "And BGP?"},
    )

    assert first.status_code == 200
    assert "event: done" in first.text
    assert second.status_code == 429
    assert second.json() == {
        "status": "error",
        "message": CHAT_RATE_LIMIT_MESSAGE,
    }
    assert int(second.headers["retry-after"]) >= 1
