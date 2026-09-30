"""SQLite FTS5 repository for document chunks."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.schema import DOCUMENT_CHUNKS_FTS_TABLE
from app.models.document import Document
from app.schemas.chunk import Chunk
from app.schemas.search import RetrievalCandidate
from app.services.tokenization import TokenizationService, get_tokenization_service

FTS_TABLE_NAME = DOCUMENT_CHUNKS_FTS_TABLE
CHUNK_INDEX_TABLE_NAME = "chunk_index"
SEARCH_TERM_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class StoredChunkRow:
    """One chunk row read back from the document search index."""

    document_id: int
    chunk_index: int
    content: str
    page: int | None
    section: str | None


class FtsChunkRepository:
    """Replace and search document chunks through SQLite FTS5."""

    def __init__(
        self,
        session: Session,
        tokenizer: TokenizationService | None = None,
    ) -> None:
        """Initialize the repository with a session and shared tokenizer."""
        self._session = session
        self._tokenizer = tokenizer or get_tokenization_service()

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
    ) -> None:
        """Replace every FTS5 row belonging to a document."""
        try:
            self._session.execute(
                text(f"DELETE FROM {FTS_TABLE_NAME} WHERE document_id = :document_id"),
                {"document_id": document.id},
            )
            rows: list[dict[str, str | int | None]] = [
                {
                    "document_id": document.id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "page": chunk.page,
                    "section": chunk.section,
                    "content_tokens": self._tokenizer.tokenize_for_index(chunk.content),
                }
                for chunk in chunks
            ]
            if rows:
                self._session.execute(
                    text(
                        f"""
                        INSERT INTO {FTS_TABLE_NAME}
                            (document_id, chunk_index, content, page, section,
                             content_tokens)
                        VALUES
                            (:document_id, :chunk_index, :content, :page, :section,
                             :content_tokens)
                        """
                    ),
                    rows,
                )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def list_stored_chunks(self) -> list[StoredChunkRow]:
        """Return every indexed chunk, ordered for a deterministic rebuild."""
        rows = self._session.execute(
            text(
                f"""
                SELECT document_id, chunk_index, content, page, section
                FROM {FTS_TABLE_NAME}
                ORDER BY document_id, chunk_index
                """
            )
        ).mappings()
        return [
            StoredChunkRow(
                document_id=int(row["document_id"]),
                chunk_index=int(row["chunk_index"]),
                content=str(row["content"]),
                page=int(row["page"]) if row["page"] is not None else None,
                section=str(row["section"]) if row["section"] is not None else None,
            )
            for row in rows
        ]

    def delete_document(self, document_id: int) -> None:
        """Delete all full-text chunks belonging to one document."""
        try:
            self._session.execute(
                text(
                    f"DELETE FROM {FTS_TABLE_NAME} " "WHERE document_id = :document_id"
                ),
                {"document_id": document_id},
            )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Return BM25-ranked FTS5 matches up to the requested limit."""
        match_query = self._tokenizer.build_match_query(query)
        if not match_query:
            return []
        statement = text(
            f"""
            SELECT
                document_id,
                chunk_index,
                content,
                page,
                section,
                bm25({FTS_TABLE_NAME}) AS score
            FROM {FTS_TABLE_NAME}
            WHERE {FTS_TABLE_NAME} MATCH :match_query
            ORDER BY score
            LIMIT :limit
            """
        )
        rows = self._session.execute(
            statement,
            {"match_query": match_query, "limit": limit},
        ).mappings()
        return [
            RetrievalCandidate(
                document_id=int(row["document_id"]),
                chunk_index=int(row["chunk_index"]),
                content=str(row["content"]),
                page=int(row["page"]) if row["page"] is not None else None,
                section=str(row["section"]) if row["section"] is not None else None,
                score=float(row["score"]),
            )
            for row in rows
        ]


@dataclass(frozen=True, slots=True)
class ChunkIndexEntry:
    """One chunk returned from the standalone SQLite FTS5 index."""

    chunk_id: str
    document_id: int
    content: str


class ChunkIndexRepository:
    """Insert, delete, and search chunks using native SQLite FTS5."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a SQLAlchemy database session."""
        self._session = session

    def insert(
        self,
        chunk_id: str,
        document_id: int,
        content: str,
        *,
        commit: bool = True,
    ) -> None:
        """Insert a chunk immediately or within the caller's transaction."""
        try:
            self._session.execute(
                text(
                    f"DELETE FROM {CHUNK_INDEX_TABLE_NAME} "
                    "WHERE chunk_id = :chunk_id"
                ),
                {"chunk_id": chunk_id},
            )
            self._session.execute(
                text(
                    f"""
                    INSERT INTO {CHUNK_INDEX_TABLE_NAME}
                        (chunk_id, document_id, content)
                    VALUES
                        (:chunk_id, :document_id, :content)
                    """
                ),
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "content": content,
                },
            )
            if commit:
                self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def delete(self, chunk_id: str) -> None:
        """Delete one indexed chunk by its stable chunk ID."""
        try:
            self._session.execute(
                text(
                    f"DELETE FROM {CHUNK_INDEX_TABLE_NAME} "
                    "WHERE chunk_id = :chunk_id"
                ),
                {"chunk_id": chunk_id},
            )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def search(self, query: str, limit: int = 10) -> list[ChunkIndexEntry]:
        """Return BM25-ranked chunks matching full-text query terms."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        terms = SEARCH_TERM_PATTERN.findall(query)
        if not terms:
            return []
        match_query = " OR ".join(f'"{term}"' for term in terms)
        rows = self._session.execute(
            text(
                f"""
                SELECT chunk_id, document_id, content
                FROM {CHUNK_INDEX_TABLE_NAME}
                WHERE {CHUNK_INDEX_TABLE_NAME} MATCH :match_query
                ORDER BY bm25({CHUNK_INDEX_TABLE_NAME})
                LIMIT :limit
                """
            ),
            {"match_query": match_query, "limit": limit},
        ).mappings()
        return [
            ChunkIndexEntry(
                chunk_id=str(row["chunk_id"]),
                document_id=int(row["document_id"]),
                content=str(row["content"]),
            )
            for row in rows
        ]
