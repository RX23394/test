"""Tests for vector, keyword, and RRF search orchestration."""

from collections.abc import Sequence
from dataclasses import fields

import pytest

from app.services.keyword_search import KeywordSearchResult
from app.services.rrf import RRFResult, RRFService, RRFSourceScore
from app.services.search import SearchService, SearchServiceResult
from app.services.vector_search import VectorSearchResult


class FakeVectorSearchService:
    """Record a question and return configured vector results."""

    def __init__(
        self,
        results: list[VectorSearchResult],
        calls: list[str] | None = None,
    ) -> None:
        """Initialize results and optional shared call log."""
        self.results = results
        self.question: str | None = None
        self.calls = calls

    def search(self, question: str) -> list[VectorSearchResult]:
        """Record and return vector search results."""
        self.question = question
        if self.calls is not None:
            self.calls.append("vector")
        return self.results


class FakeKeywordSearchService:
    """Record a question and return configured keyword results."""

    def __init__(
        self,
        results: list[KeywordSearchResult],
        calls: list[str] | None = None,
    ) -> None:
        """Initialize results and optional shared call log."""
        self.results = results
        self.question: str | None = None
        self.calls = calls

    def search(self, question: str) -> list[KeywordSearchResult]:
        """Record and return keyword search results."""
        self.question = question
        if self.calls is not None:
            self.calls.append("keyword")
        return self.results


class RecordingRRFService:
    """Record fusion order and delegate to the real RRF implementation."""

    def __init__(self, calls: list[str]) -> None:
        """Initialize the shared call log."""
        self.calls = calls

    def fuse(
        self,
        vector_results: Sequence[VectorSearchResult],
        keyword_results: Sequence[KeywordSearchResult],
    ) -> list[RRFResult]:
        """Record fusion and return real reciprocal-rank results."""
        self.calls.append("rrf")
        return RRFService().fuse(vector_results, keyword_results)


class OversizedRRFService:
    """Return more than eight fused rows to test the service boundary."""

    def fuse(
        self,
        vector_results: Sequence[VectorSearchResult],
        keyword_results: Sequence[KeywordSearchResult],
    ) -> list[RRFResult]:
        """Ignore retrieval input and return ten deterministic rows."""
        del vector_results, keyword_results
        return [
            RRFResult(
                chunk=f"chunk {index}",
                document=index,
                page=index + 1,
                section=None,
                sources=(RRFSourceScore(source="vector", original_score=0.9),),
                final_score=1.0 / (61 + index),
            )
            for index in range(10)
        ]


def shared_vector_result() -> VectorSearchResult:
    """Return a vector result shared with keyword retrieval."""
    return VectorSearchResult(
        score=0.92,
        chunk="OSPF routing",
        document=7,
        page=3,
        section="Routing",
    )


def shared_keyword_result() -> KeywordSearchResult:
    """Return a keyword result shared with vector retrieval."""
    return KeywordSearchResult(
        chunk="OSPF routing",
        bm25=-1.7,
        document=7,
        page=3,
        section="Routing",
    )


def test_search_service_drops_vector_results_below_the_relevance_floor() -> None:
    """Weak vector results are filtered before fusion reaches the caller."""
    weak_vector_result = VectorSearchResult(
        score=0.51,
        chunk="unrelated text",
        document=9,
        page=1,
        section=None,
    )
    service = SearchService(
        FakeVectorSearchService([shared_vector_result(), weak_vector_result]),
        FakeKeywordSearchService([]),
        min_vector_score=0.87,
    )

    results = service.search("OSPF")

    assert [result.document for result in results] == [7]
    assert results[0].chunk == "OSPF routing"


def test_search_service_runs_vector_keyword_then_rrf() -> None:
    """The normalized question flows through both searches before fusion."""
    calls: list[str] = []
    vector = FakeVectorSearchService([shared_vector_result()], calls)
    keyword = FakeKeywordSearchService([shared_keyword_result()], calls)

    results = SearchService(
        vector,
        keyword,
        RecordingRRFService(calls),
    ).search("  How does OSPF work?  ")

    assert calls == ["vector", "keyword", "rrf"]
    assert vector.question == "How does OSPF work?"
    assert keyword.question == "How does OSPF work?"
    assert len(results) == 1


def test_search_service_returns_required_fields_and_final_rrf_score() -> None:
    """Final output maps metadata and exposes only the fused RRF score."""
    service = SearchService(
        FakeVectorSearchService([shared_vector_result()]),
        FakeKeywordSearchService([shared_keyword_result()]),
    )

    results = service.search("OSPF")

    assert [field.name for field in fields(SearchServiceResult)] == [
        "document",
        "page",
        "section",
        "chunk",
        "score",
    ]
    assert results == [
        SearchServiceResult(
            document=7,
            page=3,
            section="Routing",
            chunk="OSPF routing",
            score=pytest.approx(2 / 61),
        )
    ]


def test_search_service_deduplicates_shared_chunk_through_rrf() -> None:
    """The same vector and keyword chunk appears once in final output."""
    vector_results = [shared_vector_result()]
    keyword_results = [
        shared_keyword_result(),
        KeywordSearchResult(
            chunk="VLAN switching",
            bm25=-1.0,
            document=8,
            page=4,
            section="Switching",
        ),
    ]

    results = SearchService(
        FakeVectorSearchService(vector_results),
        FakeKeywordSearchService(keyword_results),
    ).search("network")

    assert [result.chunk for result in results].count("OSPF routing") == 1
    assert results[0].chunk == "OSPF routing"


def test_search_service_enforces_top8_output() -> None:
    """The orchestration boundary never returns more than eight chunks."""
    results = SearchService(
        FakeVectorSearchService([]),
        FakeKeywordSearchService([]),
        OversizedRRFService(),
    ).search("network")

    assert len(results) == 8
    assert [result.chunk for result in results] == [
        f"chunk {index}" for index in range(8)
    ]


def test_search_service_rejects_blank_question_before_dependencies() -> None:
    """Blank questions do not call vector, keyword, or RRF services."""
    calls: list[str] = []
    service = SearchService(
        FakeVectorSearchService([], calls),
        FakeKeywordSearchService([], calls),
        RecordingRRFService(calls),
    )

    with pytest.raises(ValueError, match="question must not be empty"):
        service.search("  ")

    assert calls == []
