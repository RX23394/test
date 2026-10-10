"""Tests for the complete document indexing pipeline."""

from collections.abc import Iterator, Sequence
from pathlib import Path

import httpx
import numpy as np
import pytest
from numpy.typing import NDArray
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import documents as document_routes
from app.auth.security import create_access_token
from app.core.config import Settings, get_settings
from app.main import app
from app.models.document import Document, DocumentStatus
from app.rag.dependencies import (
    get_embedding_service,
    get_llm_provider,
    get_qdrant_repository,
)
from app.repositories.conversation import ConversationRepository
from app.repositories.document import DocumentRepository
from app.repositories.qdrant import QdrantChunkRepository
from app.repositories.user import UserRepository
from app.schemas.chunk import Chunk
from app.services.conversation import ConversationService
from app.services.document_parser import (
    DocumentContent,
    DocumentPage,
    Parser,
    ParserRegistry,
)
from app.services.document_parser.dependencies import get_parser_registry
from app.services.embedding import EMBEDDING_DIMENSION, EmbeddingService


class FakeMarkdownParser(Parser):
    """Return test Markdown as one page for indexing integration."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Read a test file into the page-preserving parser contract."""
        return DocumentContent(
            filename=file_path.name,
            pages=[
                DocumentPage(
                    page_number=1,
                    text=file_path.read_text(encoding="utf-8"),
                )
            ],
        )


class FixedEncoder:
    """Return deterministic vectors without loading model weights."""

    def __init__(self) -> None:
        """Initialize the recorded encoder inputs."""
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
        """Return one fixed-size vector for every prefixed passage."""
        del batch_size, show_progress_bar, convert_to_numpy, normalize_embeddings
        assert all(
            sentence.startswith(("passage: ", "query: ")) for sentence in sentences
        )
        self.sentences.extend(sentences)
        return np.ones((len(sentences), EMBEDDING_DIMENSION), dtype=np.float32)


class FixedChunkService:
    """Create deterministic test chunks without loading tiktoken data."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Split each non-empty test heading section into one chunk."""
        return [
            Chunk(
                content="Network overview.",
                page=1,
                section="Introduction",
                chunk_index=0,
            ),
            Chunk(
                content="OSPF details.",
                page=1,
                section="Routing",
                chunk_index=1,
            ),
        ]


class FixedLLMProvider:
    """Stream a deterministic answer and record citation sources."""

    def __init__(self) -> None:
        """Initialize captured source state."""
        self.messages: list[object] = []

    def stream_chat(
        self,
        messages: Sequence[object],
    ) -> Iterator[str]:
        """Record messages and yield a cited answer in two deltas."""
        self.messages = list(messages)
        yield "OSPF is a routing protocol "
        yield "[S1]."


def create_indexable_document(
    session: Session,
    upload_dir: Path,
) -> Document:
    """Create an administrator, stored Markdown file, and document record."""
    user = UserRepository(session).create(
        username="index-admin",
        password_hash="hashed-password",
        is_admin=True,
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    content = b"# Introduction\nNetwork overview.\n# Routing\nOSPF details."
    (upload_dir / "indexed.md").write_bytes(content)
    return DocumentRepository(session).create(
        filename="indexed.md",
        original_filename="guide.md",
        sha256="f" * 64,
        file_size=len(content),
        uploader_id=user.id,
    )


@pytest.mark.asyncio
async def test_index_endpoint_writes_chunks_to_qdrant(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The index endpoint runs the pipeline and persists Qdrant points."""
    settings: Settings = get_settings()
    monkeypatch.setattr(settings, "document_upload_dir", tmp_path)
    monkeypatch.setattr(document_routes, "ChunkService", FixedChunkService)
    encoder = FixedEncoder()
    qdrant_client = QdrantClient(location=":memory:")
    qdrant_repository = QdrantChunkRepository(
        url="http://unused",
        collection_name="indexed_chunks",
        client=qdrant_client,
    )

    def override_embedding_service() -> EmbeddingService:
        """Return a deterministic embedding service for the endpoint."""
        return EmbeddingService(encoder)

    def override_qdrant_repository() -> QdrantChunkRepository:
        """Return the in-memory Qdrant repository for the endpoint."""
        return qdrant_repository

    app.dependency_overrides[get_embedding_service] = override_embedding_service
    app.dependency_overrides[get_qdrant_repository] = override_qdrant_repository
    llm_provider = FixedLLMProvider()

    def override_llm_provider() -> FixedLLMProvider:
        """Return the deterministic streaming LLM provider."""
        return llm_provider

    app.dependency_overrides[get_llm_provider] = override_llm_provider

    def override_parser_registry() -> ParserRegistry:
        """Return a registry with the indexing test parser."""
        registry = ParserRegistry()
        registry.register(".md", FakeMarkdownParser())
        return registry

    app.dependency_overrides[get_parser_registry] = override_parser_registry

    with session_factory() as session:
        document = create_indexable_document(session, tmp_path)
        document_id = document.id
        uploader_id = document.uploader_id
        conversation = ConversationRepository(session).create(
            user_id=uploader_id,
        )
        conversation_id = conversation.id
    client.cookies.set(
        settings.auth_cookie_name,
        create_access_token(uploader_id),
    )

    parse_response = await client.post(f"/api/admin/documents/{document_id}/parse")
    assert parse_response.status_code == 200

    response = await client.post(f"/api/admin/documents/{document_id}/index")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "data": {"document_id": document_id, "chunk_count": 2},
    }
    points, _ = qdrant_client.scroll(
        collection_name="indexed_chunks",
        limit=10,
        with_payload=True,
    )
    assert len(points) == 2
    assert all((point.payload or {})["document_id"] == document_id for point in points)

    duplicate_index_response = await client.post(
        f"/api/admin/documents/{document_id}/index"
    )
    assert duplicate_index_response.status_code == 409
    assert duplicate_index_response.json()["message"] == "Document is already indexed"

    search_response = await client.post(
        "/api/search",
        json={"query": "Routing OSPF"},
    )
    assert search_response.status_code == 200
    search_data = search_response.json()["data"]
    assert len(search_data) == 2
    assert search_data[0]["section"] == "Routing"

    chat_response = await client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation_id, "message": "What is OSPF?"},
    )
    assert chat_response.status_code == 200
    assert chat_response.headers["content-type"].startswith("text/event-stream")
    assert "event: citation" in chat_response.text
    assert '"id":"S1"' in chat_response.text
    assert '"document":"guide.md"' in chat_response.text
    assert '"section":"Routing"' in chat_response.text
    assert '"data":"[S1]."' in chat_response.text
    assert "event: done" in chat_response.text
    assert "section: Routing" in str(llm_provider.messages)

    # A follow-up carries no retrievable terms of its own, so the previous
    # question is prepended to the embedding query and replayed to the model.
    encoder.sentences.clear()
    follow_up_response = await client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation_id, "message": "那它的缺点呢？"},
    )
    assert follow_up_response.status_code == 200
    assert encoder.sentences == ["query: What is OSPF?\n那它的缺点呢？"]
    replayed_roles = [message["role"] for message in llm_provider.messages]
    assert replayed_roles == ["system", "user", "assistant", "user"]
    assert llm_provider.messages[1]["content"] == "What is OSPF?"
    assert llm_provider.messages[2]["content"] == "OSPF is a routing protocol [S1]."

    with session_factory() as session:
        indexed_document = DocumentRepository(session).get_by_id(document_id)
        assert indexed_document is not None
        assert indexed_document.status is DocumentStatus.INDEXED
        detail = ConversationService(ConversationRepository(session)).get(
            conversation_id,
            uploader_id,
        )
        assert [message.role for message in detail.messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
