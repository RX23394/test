"""Transactional chunk indexing orchestration."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import DocumentStatus
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)


class PassageEmbeddingProvider(Protocol):
    """Passage embedding contract required by indexing."""

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for each supplied chunk text."""
        ...


class ChunkVectorRepository(Protocol):
    """Vector persistence and compensation contract."""

    def upsert_chunks(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Persist chunk vectors."""
        ...

    def delete_document(self, document_id: int) -> None:
        """Delete vectors belonging to one document."""
        ...


class ChunkTextRepository(Protocol):
    """Transactional full-text persistence contract."""

    def insert(
        self,
        chunk_id: str,
        document_id: int,
        content: str,
        *,
        commit: bool = True,
    ) -> None:
        """Insert one chunk into the active SQLite transaction."""
        ...


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Successful document indexing summary."""

    document_id: int
    chunk_count: int
    status: DocumentStatus


class IndexRollbackError(RuntimeError):
    """Raised when Qdrant compensation fails after an indexing error."""


class IndexService:
    """Embed and persist chunks with SQLite rollback and Qdrant compensation."""

    def __init__(
        self,
        session: Session,
        document_repository: DocumentRepository,
        embedding_service: PassageEmbeddingProvider,
        qdrant_repository: ChunkVectorRepository,
        fts_repository: ChunkTextRepository,
    ) -> None:
        """Initialize transactional indexing dependencies."""
        self._session = session
        self._document_repository = document_repository
        self._embedding_service = embedding_service
        self._qdrant_repository = qdrant_repository
        self._fts_repository = fts_repository

    def index(self, chunks: list[Chunk]) -> IndexResult:
        """Index one document's chunks and atomically mark it indexed."""
        document_id = self._get_document_id(chunks)
        document = self._document_repository.get_by_id(document_id)
        if document is None:
            raise ValueError(f"Document {document_id} does not exist")
        if document.status is DocumentStatus.INDEXED:
            raise ValueError("Document is already indexed")

        qdrant_write_started = False
        try:
            vectors = self._embedding_service.embed_passages(
                [chunk.text for chunk in chunks]
            )
            qdrant_write_started = True
            self._qdrant_repository.upsert_chunks(chunks, vectors)
            for chunk in chunks:
                self._fts_repository.insert(
                    chunk.id,
                    document_id,
                    chunk.text,
                    commit=False,
                )
            self._document_repository.update_status(
                document,
                DocumentStatus.INDEXED,
                commit=False,
            )
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            if qdrant_write_started:
                self._compensate_qdrant(document_id, exc)
            raise

        logger.info(
            "Document indexing completed",
            extra={"document_id": document_id, "chunk_count": len(chunks)},
        )
        return IndexResult(
            document_id=document_id,
            chunk_count=len(chunks),
            status=DocumentStatus.INDEXED,
        )

    @staticmethod
    def _get_document_id(chunks: list[Chunk]) -> int:
        """Validate that a non-empty chunk list belongs to one document."""
        if not chunks:
            raise ValueError("chunks must not be empty")
        document_ids = {chunk.document_id for chunk in chunks}
        if None in document_ids or len(document_ids) != 1:
            raise ValueError("chunks must belong to one persisted document")
        document_id = next(iter(document_ids))
        if document_id is None:
            raise ValueError("document_id is required")
        return document_id

    def _compensate_qdrant(
        self,
        document_id: int,
        original_error: Exception,
    ) -> None:
        """Delete partially written vectors or raise a rollback failure."""
        try:
            self._qdrant_repository.delete_document(document_id)
        except Exception:
            logger.exception(
                "Qdrant compensation failed",
                extra={"document_id": document_id},
            )
            raise IndexRollbackError(
                "SQLite rolled back but Qdrant compensation failed"
            ) from original_error
