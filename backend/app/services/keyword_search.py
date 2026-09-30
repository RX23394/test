"""SQLite FTS5 Top20 keyword search."""

from dataclasses import dataclass
from typing import Protocol

from app.schemas.search import RetrievalCandidate

KEYWORD_SEARCH_TOP_K = 20


class KeywordRepository(Protocol):
    """SQLite full-text search contract."""

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Return BM25-ranked full-text candidates."""
        ...


@dataclass(frozen=True, slots=True)
class KeywordSearchResult:
    """One BM25-ranked chunk with source metadata."""

    chunk: str
    bm25: float
    document: int
    page: int | None
    section: str | None


class KeywordSearchService:
    """Search user questions through SQLite FTS5 and return Top20."""

    def __init__(self, fts_repository: KeywordRepository) -> None:
        """Initialize the SQLite full-text repository dependency."""
        self._fts_repository = fts_repository

    def search(self, question: str) -> list[KeywordSearchResult]:
        """Return at most twenty BM25-ranked results for a user question."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        candidates = self._fts_repository.search(
            normalized_question,
            limit=KEYWORD_SEARCH_TOP_K,
        )
        return [
            KeywordSearchResult(
                chunk=candidate.content,
                bm25=candidate.score,
                document=candidate.document_id,
                page=candidate.page,
                section=candidate.section,
            )
            for candidate in candidates[:KEYWORD_SEARCH_TOP_K]
        ]
