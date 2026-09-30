"""Tests for transactional chunk indexing orchestration."""

from collections.abc import Sequence

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.repositories.document import DocumentRepository
from app.repositories.fts import ChunkIndexRepository
from app.repositories.user import UserRepository
from app.services.index import IndexResult, IndexRollbackError, IndexService


class FakeEmbeddingService:
    """Return deterministic vectors or fail before persistence."""

    def __init__(self, *, fail: bool = False) -> None:
        """Initialize failure and recorded text state."""
        self.fail = fail
        self.texts: list[str] = []

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Record texts and return one three-dimensional vector each."""
        self.texts = list(texts)
        if self.fail:
            raise RuntimeError("embedding failed")
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeQdrantRepository:
    """Record vectors and support compensating document deletion."""

    def __init__(
        self,
        *,
        fail_upsert: bool = False,
        fail_delete: bool = False,
    ) -> None:
        """Initialize failure modes and in-memory point storage."""
        self.fail_upsert = fail_upsert
        self.fail_delete = fail_delete
        self.stored_chunks: list[Chunk] = []
        self.vectors: list[list[float]] = []
        self.deleted_document_ids: list[int] = []

    def upsert_chunks(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Store inputs before optionally simulating a partial failure."""
        self.stored_chunks = list(chunks)
        self.vectors = [list(vector) for vector in vectors]
        if self.fail_upsert:
            raise RuntimeError("qdrant failed")

    def delete_document(self, document_id: int) -> None:
        """Compensate stored points for one document."""
        self.deleted_document_ids.append(document_id)
        if self.fail_delete:
            raise RuntimeError("qdrant compensation failed")
        self.stored_chunks = [
            chunk for chunk in self.stored_chunks if chunk.document_id != document_id
        ]
        self.vectors = []


class FailingFtsRepository:
    """Write one row then fail to exercise SQLite transaction rollback."""

    def __init__(self, repository: ChunkIndexRepository) -> None:
        """Initialize the wrapped repository and call counter."""
        self._repository = repository
        self.call_count = 0

    def insert(
        self,
        chunk_id: str,
        document_id: int,
        content: str,
        *,
        commit: bool = True,
    ) -> None:
        """Insert the first row and fail before inserting the second."""
        self.call_count += 1
        if self.call_count == 2:
            raise RuntimeError("fts failed")
        self._repository.insert(
            chunk_id,
            document_id,
            content,
            commit=commit,
        )


def create_document(session: Session) -> Document:
    """Create one pending document for indexing tests."""
    user = UserRepository(session).create(
        username="index-service-owner",
        password_hash="hashed-password",
    )
    return DocumentRepository(session).create(
        filename="stored.md",
        original_filename="guide.md",
        sha256="9" * 64,
        file_size=100,
        uploader_id=user.id,
    )


def create_chunks(document_id: int) -> list[Chunk]:
    """Create two chunks belonging to one persisted document."""
    return [
        Chunk(
            id=f"document-{document_id}-chunk-0",
            document_id=document_id,
            page=1,
            section="Routing",
            chunk_index=0,
            text="OSPF routing",
            token_count=3,
        ),
        Chunk(
            id=f"document-{document_id}-chunk-1",
            document_id=document_id,
            page=2,
            section="Switching",
            chunk_index=1,
            text="VLAN switching",
            token_count=3,
        ),
    ]


def assert_document_status(
    session: Session,
    document_id: int,
    expected: DocumentStatus,
) -> None:
    """Expire session state and assert the persisted document status."""
    session.expire_all()
    document = DocumentRepository(session).get_by_id(document_id)
    assert document is not None
    assert document.status is expected


def test_index_service_persists_all_stores_then_marks_indexed(
    session_factory: sessionmaker[Session],
) -> None:
    """Successful embedding, Qdrant, and FTS writes commit indexed status."""
    with session_factory() as session:
        document = create_document(session)
        chunks = create_chunks(document.id)
        embedding = FakeEmbeddingService()
        qdrant = FakeQdrantRepository()
        fts = ChunkIndexRepository(session)
        service = IndexService(
            session,
            DocumentRepository(session),
            embedding,
            qdrant,
            fts,
        )

        result = service.index(chunks)

        assert result == IndexResult(
            document_id=document.id,
            chunk_count=2,
            status=DocumentStatus.INDEXED,
        )
        assert embedding.texts == ["OSPF routing", "VLAN switching"]
        assert qdrant.stored_chunks == chunks
        assert len(qdrant.vectors) == 2
        assert [entry.chunk_id for entry in fts.search("routing switching")] == [
            chunks[0].id,
            chunks[1].id,
        ]
        assert_document_status(session, document.id, DocumentStatus.INDEXED)


def test_embedding_failure_leaves_all_stores_unchanged(
    session_factory: sessionmaker[Session],
) -> None:
    """Embedding failure occurs before Qdrant or SQLite persistence."""
    with session_factory() as session:
        document = create_document(session)
        qdrant = FakeQdrantRepository()
        fts = ChunkIndexRepository(session)
        service = IndexService(
            session,
            DocumentRepository(session),
            FakeEmbeddingService(fail=True),
            qdrant,
            fts,
        )

        with pytest.raises(RuntimeError, match="embedding failed"):
            service.index(create_chunks(document.id))

        assert qdrant.stored_chunks == []
        assert qdrant.deleted_document_ids == []
        assert fts.search("routing switching") == []
        assert_document_status(session, document.id, DocumentStatus.PENDING)


def test_qdrant_failure_triggers_compensation_and_sqlite_rollback(
    session_factory: sessionmaker[Session],
) -> None:
    """A partial Qdrant failure is deleted before propagating the error."""
    with session_factory() as session:
        document = create_document(session)
        qdrant = FakeQdrantRepository(fail_upsert=True)
        fts = ChunkIndexRepository(session)
        service = IndexService(
            session,
            DocumentRepository(session),
            FakeEmbeddingService(),
            qdrant,
            fts,
        )

        with pytest.raises(RuntimeError, match="qdrant failed"):
            service.index(create_chunks(document.id))

        assert qdrant.stored_chunks == []
        assert qdrant.deleted_document_ids == [document.id]
        assert fts.search("routing switching") == []
        assert_document_status(session, document.id, DocumentStatus.PENDING)


def test_fts_failure_rolls_back_rows_status_and_qdrant(
    session_factory: sessionmaker[Session],
) -> None:
    """An FTS failure rolls back its first row and compensates Qdrant."""
    with session_factory() as session:
        document = create_document(session)
        qdrant = FakeQdrantRepository()
        real_fts = ChunkIndexRepository(session)
        service = IndexService(
            session,
            DocumentRepository(session),
            FakeEmbeddingService(),
            qdrant,
            FailingFtsRepository(real_fts),
        )

        with pytest.raises(RuntimeError, match="fts failed"):
            service.index(create_chunks(document.id))

        assert qdrant.stored_chunks == []
        assert qdrant.deleted_document_ids == [document.id]
        assert real_fts.search("routing switching") == []
        assert_document_status(session, document.id, DocumentStatus.PENDING)


def test_compensation_failure_raises_consistency_error(
    session_factory: sessionmaker[Session],
) -> None:
    """A failed Qdrant compensation is surfaced as IndexRollbackError."""
    with session_factory() as session:
        document = create_document(session)
        service = IndexService(
            session,
            DocumentRepository(session),
            FakeEmbeddingService(),
            FakeQdrantRepository(fail_upsert=True, fail_delete=True),
            ChunkIndexRepository(session),
        )

        with pytest.raises(IndexRollbackError, match="compensation failed"):
            service.index(create_chunks(document.id))

        assert_document_status(session, document.id, DocumentStatus.PENDING)


def test_index_service_rejects_empty_or_mixed_document_chunks(
    session_factory: sessionmaker[Session],
) -> None:
    """A batch must be non-empty and belong to exactly one document."""
    with session_factory() as session:
        document = create_document(session)
        service = IndexService(
            session,
            DocumentRepository(session),
            FakeEmbeddingService(),
            FakeQdrantRepository(),
            ChunkIndexRepository(session),
        )
        mixed = create_chunks(document.id)
        mixed[1] = Chunk(
            id="other",
            document_id=document.id + 1,
            page=1,
            section=None,
            chunk_index=1,
            text="other",
            token_count=1,
        )

        with pytest.raises(ValueError, match="must not be empty"):
            service.index([])
        with pytest.raises(ValueError, match="one persisted document"):
            service.index(mixed)
