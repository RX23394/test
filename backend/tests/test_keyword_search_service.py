"""Tests for SQLite FTS5 Top20 keyword search."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.repositories.user import UserRepository
from app.schemas.chunk import Chunk
from app.schemas.search import RetrievalCandidate
from app.services.keyword_search import (
    KEYWORD_SEARCH_TOP_K,
    KeywordSearchResult,
    KeywordSearchService,
)


class FakeFtsRepository:
    """Record keyword searches and return configured candidates."""

    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        """Initialize candidates and recorded query state."""
        self.candidates = candidates
        self.query: str | None = None
        self.limit: int | None = None

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Record search input and intentionally ignore the limit."""
        self.query = query
        self.limit = limit
        return self.candidates


def create_candidate(index: int) -> RetrievalCandidate:
    """Create one deterministic BM25 candidate."""
    return RetrievalCandidate(
        document_id=200 + index,
        chunk_index=index,
        content=f"keyword chunk {index}",
        page=index + 1,
        section=f"section {index}",
        score=-1.0 - index / 100.0,
    )


def test_keyword_search_requests_and_enforces_top20() -> None:
    """The service requests Top20 and caps an oversized repository result."""
    repository = FakeFtsRepository([create_candidate(index) for index in range(25)])

    results = KeywordSearchService(repository).search("  OSPF routing  ")

    assert repository.query == "OSPF routing"
    assert repository.limit == KEYWORD_SEARCH_TOP_K == 20
    assert len(results) == 20


def test_keyword_search_maps_required_result_fields() -> None:
    """FTS candidates map to chunk, BM25, document, page, and section."""
    results = KeywordSearchService(FakeFtsRepository([create_candidate(0)])).search(
        "routing"
    )

    assert results == [
        KeywordSearchResult(
            chunk="keyword chunk 0",
            bm25=-1.0,
            document=200,
            page=1,
            section="section 0",
        )
    ]


def test_keyword_search_preserves_nullable_metadata() -> None:
    """Missing page and section values remain None in the output."""
    candidate = RetrievalCandidate(
        document_id=7,
        chunk_index=0,
        content="plain content",
        page=None,
        section=None,
        score=-0.5,
    )

    result = KeywordSearchService(FakeFtsRepository([candidate])).search("plain")

    assert result[0].page is None
    assert result[0].section is None


def test_keyword_search_rejects_blank_question() -> None:
    """A blank question is rejected before querying SQLite."""
    repository = FakeFtsRepository([])

    with pytest.raises(ValueError, match="question must not be empty"):
        KeywordSearchService(repository).search("  ")

    assert repository.query is None


def test_keyword_search_uses_real_sqlite_fts5(
    session_factory: sessionmaker[Session],
) -> None:
    """The service returns real FTS5 BM25 content and source metadata."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="keyword-search-owner",
            password_hash="hashed-password",
        )
        document = DocumentRepository(session).create(
            filename="stored.md",
            original_filename="guide.md",
            sha256="8" * 64,
            file_size=100,
            uploader_id=user.id,
        )
        repository = FtsChunkRepository(session)
        repository.replace_document_chunks(
            document,
            [
                Chunk(
                    content="OSPF link-state routing protocol",
                    page=3,
                    section="Routing",
                    chunk_index=0,
                ),
                Chunk(
                    content="Ethernet VLAN switching",
                    page=4,
                    section="Switching",
                    chunk_index=1,
                ),
            ],
        )

        results = KeywordSearchService(repository).search("OSPF")

    assert len(results) == 1
    assert results[0].chunk == "OSPF link-state routing protocol"
    assert isinstance(results[0].bm25, float)
    assert results[0].document == document.id
    assert results[0].page == 3
    assert results[0].section == "Routing"
