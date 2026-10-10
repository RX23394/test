"""Question-to-vector Top20 document chunk search."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.schemas.search import RetrievalCandidate

VECTOR_SEARCH_TOP_K = 30


class QueryEmbeddingProvider(Protocol):
    """Query embedding contract required by vector search."""

    def embed_query(self, text: str) -> list[list[float]]:
        """Return one query vector as a two-dimensional list."""
        ...


class VectorRepository(Protocol):
    """Vector similarity repository contract."""

    def search(
        self,
        vector: Sequence[float],
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        """Return vector-ranked retrieval candidates."""
        ...


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """One vector-ranked chunk with source metadata."""

    score: float
    chunk: str
    document: int
    page: int | None
    section: str | None


class VectorSearchService:
    """Embed a user question and return its Top20 Qdrant matches."""

    def __init__(
        self,
        embedding_service: QueryEmbeddingProvider,
        qdrant_repository: VectorRepository,
        *,
        min_score: float = 0.0,
    ) -> None:
        """Initialize query embedding, vector search, and the relevance floor."""
        self._embedding_service = embedding_service
        self._qdrant_repository = qdrant_repository
        self._min_score = min_score

    def search(self, question: str) -> list[VectorSearchResult]:
        """Embed a non-empty question and return its relevant Top30 matches."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        query_vectors = self._embedding_service.embed_query(normalized_question)
        if len(query_vectors) != 1:
            raise ValueError("embed_query must return exactly one vector")
        candidates = self._qdrant_repository.search(
            query_vectors[0],
            limit=VECTOR_SEARCH_TOP_K,
        )
        relevant = [
            candidate
            for candidate in candidates[:VECTOR_SEARCH_TOP_K]
            if candidate.score >= self._min_score
        ]
        return [
            VectorSearchResult(
                score=candidate.score,
                chunk=candidate.content,
                document=candidate.document_id,
                page=candidate.page,
                section=candidate.section,
            )
            for candidate in relevant
        ]
