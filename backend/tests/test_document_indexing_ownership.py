"""Concurrency and ownership tests for document indexing."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import documents as document_routes
from app.auth.security import create_access_token
from app.core.config import Settings, get_settings
from app.main import app
from app.models.document import Document, DocumentStatus
from app.rag.dependencies import get_embedding_service, get_qdrant_repository
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.schemas.chunk import Chunk
from app.services.document_parser import (
    DocumentContent,
    DocumentPage,
    Parser,
    ParserRegistry,
)
from app.services.document_parser.dependencies import get_parser_registry


class MarkdownParser(Parser):
    """Return one deterministic page without performing real format parsing."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Return the content that the ownership test indexes."""
        return DocumentContent(
            filename=file_path.name,
            pages=[DocumentPage(page_number=1, text="owned document content")],
        )


class OneChunkService:
    """Produce one fixed chunk without loading tokenizer resources."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Build the one chunk used by this test."""
        return [
            Chunk(
                content=document.pages[0].text,
                page=1,
                section=None,
                chunk_index=0,
            )
        ]


class BlockingEmbeddingService:
    """Hold the owning request after its claim so another request can race."""

    def __init__(self) -> None:
        """Initialize synchronization events and a deterministic vector."""
        self.entered = Event()
        self.release = Event()

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Block until the competing request has attempted its claim."""
        assert texts == ["owned document content"]
        self.entered.set()
        assert self.release.wait(timeout=5)
        return [[1.0, 0.0, 0.0]]


class FixedEmbeddingService:
    """Return one deterministic vector without blocking."""

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for the single test chunk."""
        assert texts == ["owned document content"]
        return [[1.0, 0.0, 0.0]]


class RecordingVectorRepository:
    """Record vector writes and cleanup attempts."""

    def __init__(self) -> None:
        """Initialize empty operation records."""
        self.replaced_document_ids: list[int] = []
        self.deleted_document_ids: list[int] = []

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Record an owned vector write."""
        del chunks, vectors
        self.replaced_document_ids.append(document.id)

    def delete_document(self, document_id: int) -> None:
        """Record a compensation attempt."""
        self.deleted_document_ids.append(document_id)


def create_pending_document(
    session: Session,
    upload_dir: Path,
) -> tuple[Document, int]:
    """Create an administrator, source file, and pending document."""
    admin = UserRepository(session).create(
        username="index-owner-admin",
        password_hash="hashed-password",
        is_admin=True,
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "owned.md").write_text("content", encoding="utf-8")
    document = DocumentRepository(session).create(
        filename="owned.md",
        original_filename="owned.md",
        sha256="e" * 64,
        file_size=7,
        uploader_id=admin.id,
    )
    return document, admin.id


@pytest.mark.asyncio
async def test_concurrent_index_requests_allow_only_the_claim_owner(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A competing request is rejected and cannot clean up the owner's data."""
    settings: Settings = get_settings()
    monkeypatch.setattr(settings, "document_upload_dir", tmp_path)
    embedding_service = BlockingEmbeddingService()
    vector_repository = RecordingVectorRepository()
    monkeypatch.setattr(document_routes, "ChunkService", OneChunkService)

    def parser_registry() -> ParserRegistry:
        """Return the deterministic Markdown parser."""
        registry = ParserRegistry()
        registry.register(".md", MarkdownParser())
        return registry

    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_qdrant_repository] = lambda: vector_repository
    app.dependency_overrides[get_parser_registry] = parser_registry
    with session_factory() as session:
        document, admin_id = create_pending_document(session, tmp_path)
        document_id = document.id
    client.cookies.set(settings.auth_cookie_name, create_access_token(admin_id))

    owner_request = asyncio.create_task(
        client.post(f"/api/admin/documents/{document_id}/index")
    )
    assert await asyncio.to_thread(embedding_service.entered.wait, 5)

    competing_response = await client.post(f"/api/admin/documents/{document_id}/index")
    assert competing_response.status_code == 409
    assert (
        competing_response.json()["message"]
        == "Document indexing is already in progress"
    )
    assert vector_repository.deleted_document_ids == []

    embedding_service.release.set()
    owner_response = await owner_request

    assert owner_response.status_code == 200
    assert vector_repository.replaced_document_ids == [document_id]
    assert vector_repository.deleted_document_ids == []
    with session_factory() as session:
        stored_document = DocumentRepository(session).get_by_id(document_id)
        assert stored_document is not None
        assert stored_document.status is DocumentStatus.INDEXED
        assert stored_document.indexing_job_id is None


@pytest.mark.asyncio
async def test_expired_indexing_lease_can_be_claimed_again(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A document abandoned by a dead worker is indexable again."""
    settings: Settings = get_settings()
    monkeypatch.setattr(settings, "document_upload_dir", tmp_path)
    monkeypatch.setattr(document_routes, "ChunkService", OneChunkService)
    vector_repository = RecordingVectorRepository()

    def parser_registry() -> ParserRegistry:
        """Return the deterministic Markdown parser."""
        registry = ParserRegistry()
        registry.register(".md", MarkdownParser())
        return registry

    app.dependency_overrides[get_embedding_service] = FixedEmbeddingService
    app.dependency_overrides[get_qdrant_repository] = lambda: vector_repository
    app.dependency_overrides[get_parser_registry] = parser_registry

    with session_factory() as session:
        document, admin_id = create_pending_document(session, tmp_path)
        document_id = document.id
        repository = DocumentRepository(session)
        abandoned = repository.claim_for_indexing(document_id, "dead-worker")
        assert abandoned is not None
        abandoned.indexing_started_at = datetime.now(UTC).replace(
            tzinfo=None
        ) - timedelta(minutes=30)
        session.commit()
    client.cookies.set(settings.auth_cookie_name, create_access_token(admin_id))

    response = await client.post(f"/api/admin/documents/{document_id}/index")

    assert response.status_code == 200
    assert vector_repository.replaced_document_ids == [document_id]
    with session_factory() as session:
        stored_document = DocumentRepository(session).get_by_id(document_id)
        assert stored_document is not None
        assert stored_document.status is DocumentStatus.INDEXED
        assert stored_document.indexing_job_id is None
        assert stored_document.indexing_started_at is None


def test_repository_requires_the_claim_owner_to_finish_or_fail(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    """Only the UUID that won the conditional update can finalize the task."""
    with session_factory() as session:
        document, _ = create_pending_document(session, tmp_path)
        document_id = document.id

    with session_factory() as owner_session, session_factory() as other_session:
        owner_repository = DocumentRepository(owner_session)
        other_repository = DocumentRepository(other_session)
        claimed = owner_repository.claim_for_indexing(document_id, "owner-a")

        assert claimed is not None
        assert claimed.status is DocumentStatus.PROCESSING
        assert claimed.indexing_job_id == "owner-a"
        assert other_repository.claim_for_indexing(document_id, "owner-b") is None
        assert not other_repository.complete_indexing(document_id, "owner-b")
        assert not other_repository.fail_indexing(document_id, "owner-b")
        assert owner_repository.complete_indexing(document_id, "owner-a")

    with session_factory() as session:
        stored_document = DocumentRepository(session).get_by_id(document_id)
        assert stored_document is not None
        assert stored_document.status is DocumentStatus.INDEXED
        assert stored_document.indexing_job_id is None
