"""Tests for question-to-vector Top20 search."""

from collections.abc import Sequence

import numpy as np
import pytest
from numpy.typing import NDArray

from app.schemas.search import RetrievalCandidate
from app.services.embedding import EMBEDDING_DIMENSION, EmbeddingService
from app.services.vector_search import (
    VECTOR_SEARCH_TOP_K,
    VectorSearchResult,
    VectorSearchService,
)


class FakeSentenceEncoder:
    """Record the prefixed query and return one fixed vector."""

    def __init__(self) -> None:
        """Initialize recorded sentences."""
        self.sentences: list[str] = []

    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> NDArray[np.float32]:
        """Record model inputs and return a deterministic query vector."""
        del batch_size, show_progress_bar, convert_to_numpy, normalize_embeddings
        self.sentences = sentences
        return np.ones((len(sentences), EMBEDDING_DIMENSION), dtype=np.float32)


class FakeQdrantRepository:
    """Record vector search input and return configured candidates."""

    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        """Initialize candidates and recorded search state."""
        self.candidates = candidates
        self.vector: list[float] = []
        self.limit: int | None = None

    def search(
        self,
        vector: Sequence[float],
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        """Record the vector and intentionally ignore the requested limit."""
        self.vector = list(vector)
        self.limit = limit
        return self.candidates


def create_candidate(index: int) -> RetrievalCandidate:
    """Create one deterministic ranked Qdrant candidate."""
    return RetrievalCandidate(
        document_id=100 + index,
        chunk_index=index,
        content=f"chunk content {index}",
        page=index + 1,
        section=f"section {index}",
        score=1.0 - index / 100.0,
    )


def test_vector_search_adds_query_prefix_and_requests_top20() -> None:
    """The service embeds with query prefix and requests exactly Top20."""
    encoder = FakeSentenceEncoder()
    repository = FakeQdrantRepository([create_candidate(index) for index in range(25)])
    service = VectorSearchService(EmbeddingService(encoder), repository)

    results = service.search("  How does OSPF work?  ")

    assert encoder.sentences == ["query: How does OSPF work?"]
    assert repository.limit == VECTOR_SEARCH_TOP_K == 20
    assert len(repository.vector) == EMBEDDING_DIMENSION
    assert len(results) == 20


def test_vector_search_maps_required_result_fields() -> None:
    """Qdrant candidates map to score, chunk, document, page, and section."""
    encoder = FakeSentenceEncoder()
    repository = FakeQdrantRepository([create_candidate(0)])

    results = VectorSearchService(
        EmbeddingService(encoder),
        repository,
    ).search("OSPF")

    assert results == [
        VectorSearchResult(
            score=1.0,
            chunk="chunk content 0",
            document=100,
            page=1,
            section="section 0",
        )
    ]


def test_vector_search_preserves_nullable_source_metadata() -> None:
    """Missing page and section metadata remain None in search output."""
    candidate = RetrievalCandidate(
        document_id=7,
        chunk_index=0,
        content="plain text",
        page=None,
        section=None,
        score=0.75,
    )

    results = VectorSearchService(
        EmbeddingService(FakeSentenceEncoder()),
        FakeQdrantRepository([candidate]),
    ).search("plain")

    assert results[0].page is None
    assert results[0].section is None


def test_vector_search_rejects_blank_question() -> None:
    """A blank user question is rejected before embedding or search."""
    encoder = FakeSentenceEncoder()
    repository = FakeQdrantRepository([])

    with pytest.raises(ValueError, match="question must not be empty"):
        VectorSearchService(EmbeddingService(encoder), repository).search("  ")

    assert encoder.sentences == []
    assert repository.limit is None
