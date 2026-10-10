"""Tests for production document indexing compensation."""

from collections.abc import Sequence

import pytest

from app.models.document import Document, DocumentStatus
from app.schemas.chunk import Chunk
from app.services.document_parser import DocumentContent, DocumentPage
from app.services.indexing import (
    DocumentIndexConsistencyError,
    DocumentIndexingService,
    DocumentIndexOwnershipError,
    DocumentTextEmptyError,
)


class FakeDocumentRepository:
    """Model one claimed indexing job and record ownership transitions."""

    def __init__(self, *, fail_completion: bool = False) -> None:
        """Initialize recorded states and the final-status failure mode."""
        self.fail_completion = fail_completion
        self.statuses: list[DocumentStatus] = []
        self.owner_job_id = "owner-a"

    def is_indexing_owner(self, document_id: int, job_id: str) -> bool:
        """Return whether this fake job remains the active owner."""
        return document_id == 7 and job_id == self.owner_job_id

    def complete_indexing(self, document_id: int, job_id: str) -> bool:
        """Record the owned successful completion transition."""
        if not self.is_indexing_owner(document_id, job_id):
            return False
        self.statuses.append(DocumentStatus.INDEXED)
        if self.fail_completion:
            raise RuntimeError("status commit failed")
        self.owner_job_id = ""
        return True

    def fail_indexing(self, document_id: int, job_id: str) -> bool:
        """Record the owned failed completion transition."""
        if not self.is_indexing_owner(document_id, job_id):
            return False
        self.statuses.append(DocumentStatus.FAILED)
        self.owner_job_id = ""
        return True

    def update_status(self, document: Document, status: DocumentStatus) -> Document:
        """Record a status update for detached document test setup."""
        self.statuses.append(status)
        document.status = status
        return document


class FakeParser:
    """Return one deterministic parsed page."""

    def parse(self, document: Document) -> DocumentContent:
        """Return parsed content for the supplied document."""
        return DocumentContent(
            filename=document.filename,
            pages=[DocumentPage(page_number=1, text="OSPF routing")],
        )


class FakeChunker:
    """Return one deterministic retrieval chunk."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Create one chunk from parsed content."""
        return [
            Chunk(
                content=document.pages[0].text,
                page=1,
                section="Routing",
                chunk_index=0,
            )
        ]


class FakeEmbeddingProvider:
    """Return one deterministic vector for each chunk."""

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Create fixed vectors after validating the supplied text."""
        assert texts == ["OSPF routing"]
        return [[1.0, 0.0, 0.0]]


class FakeVectorRepository:
    """Record vector replacement and compensation calls."""

    def __init__(
        self,
        *,
        fail_replace: bool = False,
        fail_delete: bool = False,
    ) -> None:
        """Initialize vector failure modes and recorded calls."""
        self.fail_replace = fail_replace
        self.fail_delete = fail_delete
        self.replaced = False
        self.deleted_document_ids: list[int] = []

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Record replacement and optionally simulate a partial write."""
        del document, chunks, vectors
        self.replaced = True
        if self.fail_replace:
            raise RuntimeError("vector write failed")

    def delete_document(self, document_id: int) -> None:
        """Record compensation and optionally fail it."""
        self.deleted_document_ids.append(document_id)
        if self.fail_delete:
            raise RuntimeError("vector compensation failed")


class FakeTextRepository:
    """Record full-text replacement and compensation calls."""

    def __init__(self, *, fail_replace: bool = False) -> None:
        """Initialize the text replacement failure mode."""
        self.fail_replace = fail_replace
        self.replaced = False
        self.deleted_document_ids: list[int] = []

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
    ) -> None:
        """Record replacement and optionally fail it."""
        del document, chunks
        self.replaced = True
        if self.fail_replace:
            raise RuntimeError("text write failed")

    def delete_document(self, document_id: int) -> None:
        """Record full-text compensation."""
        self.deleted_document_ids.append(document_id)


def create_document() -> Document:
    """Create one detached pending document for service tests."""
    return Document(
        id=7,
        filename="stored.md",
        original_filename="guide.md",
        sha256="a" * 64,
        file_size=12,
        uploader_id=3,
        status=DocumentStatus.PENDING,
    )


def create_service(
    document_repository: FakeDocumentRepository,
    vector_repository: FakeVectorRepository,
    text_repository: FakeTextRepository,
) -> DocumentIndexingService:
    """Create an indexing service from deterministic test dependencies."""
    return DocumentIndexingService(
        document_repository=document_repository,
        parsing_service=FakeParser(),
        chunk_service=FakeChunker(),
        embedding_service=FakeEmbeddingProvider(),
        vector_repository=vector_repository,
        text_repository=text_repository,
    )


def test_successful_index_marks_document_indexed() -> None:
    """Successful writes mark the document indexed without compensation."""
    document = create_document()
    documents = FakeDocumentRepository()
    vectors = FakeVectorRepository()
    texts = FakeTextRepository()

    result = create_service(documents, vectors, texts).index(document, "owner-a")

    assert result.chunk_count == 1
    assert documents.statuses == [DocumentStatus.INDEXED]
    assert vectors.deleted_document_ids == []
    assert texts.deleted_document_ids == []


def test_text_failure_compensates_both_search_stores() -> None:
    """A full-text failure deletes possible vector and text partial writes."""
    document = create_document()
    documents = FakeDocumentRepository()
    vectors = FakeVectorRepository()
    texts = FakeTextRepository(fail_replace=True)

    with pytest.raises(RuntimeError, match="text write failed"):
        create_service(documents, vectors, texts).index(document, "owner-a")

    assert vectors.deleted_document_ids == [document.id]
    assert texts.deleted_document_ids == [document.id]
    assert documents.statuses == [DocumentStatus.FAILED]


def test_completion_failure_also_compensates_search_stores() -> None:
    """A failed final status commit cannot leave searchable chunks behind."""
    document = create_document()
    documents = FakeDocumentRepository(fail_completion=True)
    vectors = FakeVectorRepository()
    texts = FakeTextRepository()

    with pytest.raises(RuntimeError, match="status commit failed"):
        create_service(documents, vectors, texts).index(document, "owner-a")

    assert vectors.deleted_document_ids == [document.id]
    assert texts.deleted_document_ids == [document.id]
    assert documents.statuses == [DocumentStatus.INDEXED, DocumentStatus.FAILED]


def test_compensation_failure_raises_consistency_error() -> None:
    """An incomplete cleanup is exposed as a dedicated consistency error."""
    document = create_document()
    documents = FakeDocumentRepository()
    vectors = FakeVectorRepository(fail_replace=True, fail_delete=True)
    texts = FakeTextRepository()

    with pytest.raises(DocumentIndexConsistencyError):
        create_service(documents, vectors, texts).index(document, "owner-a")

    assert vectors.deleted_document_ids == [document.id]
    assert texts.deleted_document_ids == [document.id]
    assert documents.statuses == [DocumentStatus.FAILED]


def test_non_owner_cannot_complete_or_compensate() -> None:
    """A job that does not own processing cannot alter another job's work."""
    document = create_document()
    documents = FakeDocumentRepository()
    vectors = FakeVectorRepository()
    texts = FakeTextRepository()

    with pytest.raises(DocumentIndexOwnershipError):
        create_service(documents, vectors, texts).index(document, "owner-b")

    assert documents.statuses == []
    assert vectors.deleted_document_ids == []
    assert texts.deleted_document_ids == []


class EmptyChunker:
    """Return no chunk, like a scanned PDF without a text layer."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Return an empty chunk list."""
        del document
        return []


class BlankChunker:
    """Return a chunk whose text carries no searchable content."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Return one whitespace-only chunk."""
        del document
        return [Chunk(content=" \n\t ", page=1, section=None, chunk_index=0)]


def create_service_with_chunker(
    chunker: object,
    document_repository: FakeDocumentRepository,
    vector_repository: FakeVectorRepository,
    text_repository: FakeTextRepository,
) -> DocumentIndexingService:
    """Create an indexing service whose chunker yields no searchable text."""
    return DocumentIndexingService(
        document_repository=document_repository,
        parsing_service=FakeParser(),
        chunk_service=chunker,  # type: ignore[arg-type]
        embedding_service=FakeEmbeddingProvider(),
        vector_repository=vector_repository,
        text_repository=text_repository,
    )


@pytest.mark.parametrize("chunker", [EmptyChunker(), BlankChunker()])
def test_document_without_searchable_text_is_marked_failed(chunker: object) -> None:
    """Zero searchable chunks fail the job instead of reporting empty success."""
    document = create_document()
    documents = FakeDocumentRepository()
    vectors = FakeVectorRepository()
    texts = FakeTextRepository()

    with pytest.raises(DocumentTextEmptyError, match="no searchable text"):
        create_service_with_chunker(chunker, documents, vectors, texts).index(
            document,
            "owner-a",
        )

    assert documents.statuses == [DocumentStatus.FAILED]
    assert vectors.replaced is False
    assert texts.replaced is False
    assert vectors.deleted_document_ids == []
    assert texts.deleted_document_ids == []
