"""Document parsing, chunking, embedding, and indexing orchestration."""

import logging
from collections.abc import Sequence
from typing import Protocol

from app.models.document import Document
from app.schemas.chunk import Chunk
from app.schemas.indexing import DocumentIndexResult
from app.services.document_parser import DocumentContent

logger = logging.getLogger(__name__)


class DocumentStatusRepository(Protocol):
    """Document status persistence required by indexing."""

    def is_indexing_owner(self, document_id: int, job_id: str) -> bool:
        """Return whether a job still owns a document indexing task."""
        ...

    def complete_indexing(self, document_id: int, job_id: str) -> bool:
        """Atomically complete an owned document indexing task."""
        ...

    def fail_indexing(self, document_id: int, job_id: str) -> bool:
        """Atomically fail an owned document indexing task."""
        ...


class DocumentParser(Protocol):
    """Document parsing contract required by indexing."""

    def parse(self, document: Document) -> DocumentContent:
        """Extract normalized document content."""
        ...


class DocumentChunker(Protocol):
    """Document chunking contract required by indexing."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Split parsed content into retrieval chunks."""
        ...


class PassageEmbeddingProvider(Protocol):
    """Passage embedding contract required by indexing."""

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for each supplied chunk text."""
        ...


class ChunkVectorRepository(Protocol):
    """Persistence contract required by the indexing service."""

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Replace all indexed chunks belonging to a document."""
        ...

    def delete_document(self, document_id: int) -> None:
        """Delete all vectors belonging to a document."""
        ...


class ChunkTextRepository(Protocol):
    """Full-text persistence contract required by the indexing service."""

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
    ) -> None:
        """Replace all full-text chunks belonging to a document."""
        ...

    def delete_document(self, document_id: int) -> None:
        """Delete all full-text chunks belonging to a document."""
        ...


class DocumentIndexError(RuntimeError):
    """Raised when embedding generation or vector persistence fails."""


class DocumentIndexConsistencyError(DocumentIndexError):
    """Raised when an indexing failure cannot be fully compensated."""


class DocumentIndexOwnershipError(DocumentIndexError):
    """Raised when an indexing job no longer owns its document task."""


class DocumentIndexingService:
    """Run the complete non-chat document indexing pipeline."""

    def __init__(
        self,
        document_repository: DocumentStatusRepository,
        parsing_service: DocumentParser,
        chunk_service: DocumentChunker,
        embedding_service: PassageEmbeddingProvider,
        vector_repository: ChunkVectorRepository,
        text_repository: ChunkTextRepository,
    ) -> None:
        """Initialize all indexing pipeline dependencies."""
        self._document_repository = document_repository
        self._parsing_service = parsing_service
        self._chunk_service = chunk_service
        self._embedding_service = embedding_service
        self._vector_repository = vector_repository
        self._text_repository = text_repository

    def index(self, document: Document, job_id: str) -> DocumentIndexResult:
        """Index a document and compensate both search stores on failure."""
        persistence_started = False
        try:
            self._require_ownership(document.id, job_id)
            content = self._parsing_service.parse(document)
            self._require_ownership(document.id, job_id)
            chunks = self._chunk_service.create_chunks(content)
            self._require_ownership(document.id, job_id)
            vectors = self._embedding_service.embed_passages(
                [chunk.content for chunk in chunks]
            )
            self._require_ownership(document.id, job_id)
            persistence_started = True
            self._vector_repository.replace_document_chunks(
                document,
                chunks,
                vectors,
            )
            self._require_ownership(document.id, job_id)
            self._text_repository.replace_document_chunks(document, chunks)
            if not self._document_repository.complete_indexing(document.id, job_id):
                raise DocumentIndexOwnershipError("Indexing job ownership was lost")
        except Exception as exc:
            compensation_errors = self._recover_failed_index(
                document,
                job_id=job_id,
                persistence_started=persistence_started,
            )
            logger.exception(
                "Document indexing failed",
                extra={"document_id": document.id},
            )
            if compensation_errors:
                logger.error(
                    "Document index compensation was incomplete",
                    extra={
                        "document_id": document.id,
                        "compensation_errors": compensation_errors,
                    },
                )
                raise DocumentIndexConsistencyError(
                    "Document indexing failed and compensation was incomplete"
                ) from exc
            if isinstance(exc, (OSError, RuntimeError, ValueError)):
                raise
            raise DocumentIndexError from exc

        logger.info(
            "Document indexed",
            extra={"document_id": document.id, "chunk_count": len(chunks)},
        )
        return DocumentIndexResult(
            document_id=document.id,
            chunk_count=len(chunks),
        )

    def _recover_failed_index(
        self,
        document: Document,
        *,
        job_id: str,
        persistence_started: bool,
    ) -> list[str]:
        """Compensate search writes and persist a failed document status."""
        errors: list[str] = []
        if not self._document_repository.is_indexing_owner(document.id, job_id):
            return errors
        if persistence_started:
            for store_name, delete_document in (
                ("vector", self._vector_repository.delete_document),
                ("text", self._text_repository.delete_document),
            ):
                try:
                    delete_document(document.id)
                except Exception:
                    logger.exception(
                        "Document index store compensation failed",
                        extra={
                            "document_id": document.id,
                            "store": store_name,
                        },
                    )
                    errors.append(store_name)
        try:
            if not self._document_repository.fail_indexing(document.id, job_id):
                return errors
        except Exception:
            logger.exception(
                "Failed to persist document indexing failure status",
                extra={"document_id": document.id},
            )
            errors.append("status")
        return errors

    def _require_ownership(self, document_id: int, job_id: str) -> None:
        """Reject work after the database task ownership has changed."""
        if not self._document_repository.is_indexing_owner(document_id, job_id):
            raise DocumentIndexOwnershipError("Indexing job ownership was lost")
