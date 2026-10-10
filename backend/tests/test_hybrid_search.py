"""Tests for reciprocal-rank-fused hybrid retrieval."""

from collections.abc import Sequence

from app.schemas.search import RetrievalCandidate
from app.services.search import (
    FTS_SEARCH_LIMIT,
    HYBRID_RESULT_LIMIT,
    VECTOR_SEARCH_LIMIT,
    HybridSearchService,
)


class FakeQueryEmbeddingProvider:
    """Record query embedding input and return a fixed vector."""

    def __init__(self) -> None:
        """Initialize recorded query state."""
        self.query: str | None = None

    def embed_query(self, query: str) -> list[list[float]]:
        """Record the query and return a deterministic vector."""
        self.query = query
        return [[0.5, 0.5]]


class FakeVectorRepository:
    """Return configured candidates and record the requested limit."""

    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        """Initialize the fake vector result set."""
        self._candidates = candidates
        self.limit: int | None = None

    def search(
        self,
        vector: Sequence[float],
        limit: int,
    ) -> list[RetrievalCandidate]:
        """Return vector candidates up to the requested limit."""
        del vector
        self.limit = limit
        return self._candidates[:limit]


class FakeTextRepository:
    """Return configured candidates and record the requested limit."""

    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        """Initialize the fake FTS5 result set."""
        self._candidates = candidates
        self.limit: int | None = None

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Return text candidates up to the requested limit."""
        del query
        self.limit = limit
        return self._candidates[:limit]


def make_candidate(chunk_index: int) -> RetrievalCandidate:
    """Create one ranked candidate for an RRF test."""
    return RetrievalCandidate(
        document_id=1,
        chunk_index=chunk_index,
        content=f"chunk {chunk_index}",
        score=1.0,
    )


def test_hybrid_search_uses_top30_rrf_and_returns_top8() -> None:
    """Overlapping candidates are RRF boosted and the result is limited to eight."""
    embedding_provider = FakeQueryEmbeddingProvider()
    vector_repository = FakeVectorRepository(
        [make_candidate(index) for index in range(30)]
    )
    text_repository = FakeTextRepository(
        [make_candidate(index) for index in range(7, 27)]
    )
    service = HybridSearchService(
        embedding_provider,
        vector_repository,
        text_repository,
    )

    results = service.search("routing")

    assert embedding_provider.query == "routing"
    assert vector_repository.limit == VECTOR_SEARCH_LIMIT == 30
    assert text_repository.limit == FTS_SEARCH_LIMIT == 20
    assert len(results) == HYBRID_RESULT_LIMIT == 8
    assert results[0].chunk_index == 7
    assert {result.chunk_index for result in results}.issubset(set(range(7, 30)))


def test_hybrid_search_drops_vector_candidates_below_the_relevance_floor() -> None:
    """Weak vector matches never reach the prompt, even when keywords boost them."""
    weak_vector_candidate = RetrievalCandidate(
        document_id=1,
        chunk_index=0,
        content="unrelated chunk",
        score=0.5,
    )
    strong_vector_candidate = RetrievalCandidate(
        document_id=1,
        chunk_index=1,
        content="relevant chunk",
        score=0.93,
    )
    text_candidate = RetrievalCandidate(
        document_id=1,
        chunk_index=2,
        content="keyword-only chunk",
        score=1.0,
    )
    service = HybridSearchService(
        FakeQueryEmbeddingProvider(),
        FakeVectorRepository([weak_vector_candidate, strong_vector_candidate]),
        FakeTextRepository([text_candidate]),
        min_vector_score=0.87,
    )

    results = service.search("routing")

    assert {result.chunk_index for result in results} == {1, 2}


def test_hybrid_search_returns_nothing_without_any_relevant_candidate() -> None:
    """An empty knowledge base leaves the insufficient-knowledge path reachable."""
    weak_candidate = RetrievalCandidate(
        document_id=1,
        chunk_index=0,
        content="unrelated chunk",
        score=0.42,
    )
    service = HybridSearchService(
        FakeQueryEmbeddingProvider(),
        FakeVectorRepository([weak_candidate]),
        FakeTextRepository([]),
        min_vector_score=0.87,
    )

    assert service.search("routing") == []
