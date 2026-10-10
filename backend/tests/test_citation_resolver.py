"""Tests for database-backed citation resolution."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.schemas.search import SearchResult
from app.services.citation_resolver import (
    CITATION_LIMIT,
    Citation,
    CitationResolutionError,
    CitationResolver,
)


def create_result(document_id: int, index: int = 0) -> SearchResult:
    """Create one deterministic retrieval result."""
    return SearchResult(
        document_id=document_id,
        chunk_index=index,
        content=f"Original database chunk {index + 1}",
        page=12 + index,
        section=f"Area {index + 1}",
        score=0.1,
    )


def test_citation_resolver_uses_database_filename_and_chunk_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    """A source label resolves to the real stored document metadata."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="citation-owner",
            password_hash="hash",
        )
        document = DocumentRepository(session).create(
            filename="stored-f3a9.pdf",
            original_filename="Cisco OSPF.pdf",
            sha256="a" * 64,
            file_size=100,
            uploader_id=user.id,
        )
        result = create_result(document.id)

        citations = CitationResolver(DocumentRepository(session)).resolve([result])

        assert citations == [
            Citation(
                id="S1",
                document="Cisco OSPF.pdf",
                page=12,
                section="Area 1",
                content="Original database chunk 1",
            )
        ]
        assert citations[0].document != document.filename


def test_citation_resolver_preserves_rank_labels_and_top8_limit(
    session_factory: sessionmaker[Session],
) -> None:
    """Database citations retain retrieval order and stable S labels."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="citation-rank-owner",
            password_hash="hash",
        )
        document = DocumentRepository(session).create(
            filename="stored.pdf",
            original_filename="Ranked.pdf",
            sha256="b" * 64,
            file_size=100,
            uploader_id=user.id,
        )
        results = [create_result(document.id, index) for index in range(10)]

        citations = CitationResolver(DocumentRepository(session)).resolve(results)

        assert len(citations) == CITATION_LIMIT
        assert [citation.id for citation in citations] == [
            f"S{index}" for index in range(1, 9)
        ]
        assert citations[-1].content == "Original database chunk 8"


def test_citation_resolver_rejects_missing_database_document(
    session_factory: sessionmaker[Session],
) -> None:
    """Missing metadata fails instead of fabricating a visible source."""
    with session_factory() as session:
        resolver = CitationResolver(DocumentRepository(session))

        with pytest.raises(
            CitationResolutionError,
            match="Document 999 is unavailable",
        ):
            resolver.resolve([create_result(999)])
