"""SQLite FTS5 repository for document chunks.

The search index is an external-content FTS5 table: chunks live in
``document_chunk_rows`` and the virtual table only holds the token stream, kept
in step by triggers. Document-scoped cleanup therefore deletes from an ordinary
indexed table instead of scanning a virtual one.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.schema import (
    DOCUMENT_CHUNK_ROWS_TABLE,
    DOCUMENT_CHUNKS_FTS_TABLE,
)
from app.models.document import Document
from app.schemas.chunk import Chunk
from app.schemas.search import RetrievalCandidate
from app.services.tokenization import TokenizationService, get_tokenization_service

FTS_TABLE_NAME = DOCUMENT_CHUNKS_FTS_TABLE
CHUNK_ROWS_TABLE_NAME = DOCUMENT_CHUNK_ROWS_TABLE


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
        """Replace every stored chunk of a document and reindex it.

        Deletes go through the indexed ``document_id`` column of the content
        table; the triggers mirror both the delete and the insert into FTS5.
        """
        self._session.execute(
            text(
                f"DELETE FROM {CHUNK_ROWS_TABLE_NAME} "
                "WHERE document_id = :document_id"
            ),
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
                    INSERT INTO {CHUNK_ROWS_TABLE_NAME}
                        (document_id, chunk_index, content, page, section,
                         content_tokens)
                    VALUES
                        (:document_id, :chunk_index, :content, :page, :section,
                         :content_tokens)
                    """
                ),
                rows,
            )

    def list_stored_chunks(self) -> list[StoredChunkRow]:
        """Return every indexed chunk, ordered for a deterministic rebuild."""
        rows = self._session.execute(
            text(
                f"""
                SELECT document_id, chunk_index, content, page, section
                FROM {CHUNK_ROWS_TABLE_NAME}
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
        """Delete all stored chunks belonging to one document.

        The delete stays inside the caller's transaction, which is what lets a
        multi-store flow commit index cleanup and row deletion together.
        """
        self._session.execute(
            text(
                f"DELETE FROM {CHUNK_ROWS_TABLE_NAME} "
                "WHERE document_id = :document_id"
            ),
            {"document_id": document_id},
        )

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Return BM25-ranked FTS5 matches up to the requested limit."""
        match_query = self._tokenizer.build_match_query(query)
        if not match_query:
            return []
        statement = text(
            f"""
            SELECT
                rows.document_id,
                rows.chunk_index,
                rows.content,
                rows.page,
                rows.section,
                bm25({FTS_TABLE_NAME}) AS score
            FROM {FTS_TABLE_NAME}
            JOIN {CHUNK_ROWS_TABLE_NAME} AS rows
                ON rows.id = {FTS_TABLE_NAME}.rowid
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
