"""Tests for the retrieval-only search API."""

from collections.abc import Sequence

import httpx
import numpy as np
import pytest
from numpy.typing import NDArray
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token
from app.core.config import get_settings
from app.main import app
from app.rag.dependencies import (
    get_embedding_service,
    get_llm_provider,
    get_qdrant_repository,
)
from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.repositories.user import UserRepository
from app.schemas.chunk import Chunk
from app.schemas.search import RetrievalCandidate
from app.services.embedding import EMBEDDING_DIMENSION, EmbeddingService


class FakeSentenceEncoder:
    """Record the query prefix and return one deterministic vector."""

    def __init__(self) -> None:
        """Initialize recorded model input."""
        self.sentences: list[str] = []

    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> NDArray[np.float32]:
        """Record input and return fixed-size vectors without model loading."""
        del batch_size, show_progress_bar, convert_to_numpy, normalize_embeddings
        self.sentences = sentences
        return np.ones((len(sentences), EMBEDDING_DIMENSION), dtype=np.float32)


class FakeQdrantRepository:
    """Return configured vector candidates without an external connection."""

    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        """Initialize candidates and recorded vector request."""
        self.candidates = candidates
        self.vector: list[float] = []
        self.limit: int | None = None

    def search(
        self,
        vector: Sequence[float],
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        """Record and return candidates up to the requested limit."""
        self.vector = list(vector)
        self.limit = limit
        return self.candidates[:limit]


@pytest.mark.asyncio
async def test_search_api_returns_retrieval_results_without_chat_model(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """The endpoint returns filename metadata and never resolves Chat service."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="search-api-user",
            password_hash="hashed-password",
        )
        document = DocumentRepository(session).create(
            filename="stored.pdf",
            original_filename="Cisco_OSPF.pdf",
            sha256="7" * 64,
            file_size=100,
            uploader_id=user.id,
        )
        FtsChunkRepository(session).replace_document_chunks(
            document,
            [
                Chunk(
                    content="OSPF area design",
                    page=12,
                    section="Area",
                    chunk_index=0,
                )
            ],
        )
        document_id = document.id
        user_id = user.id

    encoder = FakeSentenceEncoder()
    qdrant = FakeQdrantRepository(
        [
            RetrievalCandidate(
                document_id=document_id,
                chunk_index=0,
                content="OSPF area design",
                page=12,
                section="Area",
                score=0.93,
            )
        ]
    )
    chat_calls: list[str] = []

    def override_embedding() -> EmbeddingService:
        """Return an embedding service backed by the fake encoder."""
        return EmbeddingService(encoder)

    def override_qdrant() -> FakeQdrantRepository:
        """Return a deterministic vector repository."""
        return qdrant

    def forbidden_chat_service() -> None:
        """Fail if the retrieval endpoint resolves a Chat dependency."""
        chat_calls.append("called")
        raise AssertionError("Chat service must not be called")

    app.dependency_overrides[get_embedding_service] = override_embedding
    app.dependency_overrides[get_qdrant_repository] = override_qdrant
    app.dependency_overrides[get_llm_provider] = forbidden_chat_service
    settings = get_settings()
    client.cookies.set(settings.auth_cookie_name, create_access_token(user_id))
    query = "\u4ec0\u4e48\u662f OSPF\uff1f"

    response = await client.post("/api/search", json={"query": query})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["data"]) == 1
    # The chunk is now found by both retrievers, so RRF fuses two ranks.
    # Before the Chinese tokenization fix the keyword path could not match the
    # Latin "OSPF" inside the Chinese query, and the score was only 1/61.
    assert payload["data"][0] == {
        "document": "Cisco_OSPF.pdf",
        "page": 12,
        "section": "Area",
        "content": "OSPF area design",
        "score": pytest.approx(2 / 61),
    }
    assert encoder.sentences == [f"query: {query}"]
    assert qdrant.limit == 20
    assert chat_calls == []


@pytest.mark.asyncio
async def test_search_api_validates_query_before_retrieval(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> None:
    """A missing query receives the uniform validation error response."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="search-validation-user",
            password_hash="hashed-password",
        )
        user_id = user.id

    def override_embedding() -> EmbeddingService:
        """Avoid loading model weights during request validation."""
        return EmbeddingService(FakeSentenceEncoder())

    def override_qdrant() -> FakeQdrantRepository:
        """Avoid any external vector dependency during validation."""
        return FakeQdrantRepository([])

    app.dependency_overrides[get_embedding_service] = override_embedding
    app.dependency_overrides[get_qdrant_repository] = override_qdrant
    settings = get_settings()
    client.cookies.set(settings.auth_cookie_name, create_access_token(user_id))

    response = await client.post("/api/search", json={})

    assert response.status_code == 422
    assert response.json() == {
        "status": "error",
        "message": "Request validation failed",
    }
