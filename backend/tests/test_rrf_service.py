"""Tests for reciprocal rank fusion."""

import pytest

from app.services.keyword_search import KeywordSearchResult
from app.services.rrf import (
    RRF_DEFAULT_K,
    RRF_OUTPUT_LIMIT,
    RRFService,
    RRFSourceScore,
)
from app.services.vector_search import VectorSearchResult


def vector_result(
    index: int,
    *,
    chunk: str | None = None,
    document: int | None = None,
    page: int | None = 1,
    section: str | None = "Routing",
    score: float = 0.9,
) -> VectorSearchResult:
    """Create one vector result for fusion tests."""
    return VectorSearchResult(
        score=score,
        chunk=chunk or f"chunk {index}",
        document=document if document is not None else index + 1,
        page=page,
        section=section,
    )


def keyword_result(
    index: int,
    *,
    chunk: str | None = None,
    document: int | None = None,
    page: int | None = 1,
    section: str | None = "Routing",
    bm25: float = -1.0,
) -> KeywordSearchResult:
    """Create one keyword result for fusion tests."""
    return KeywordSearchResult(
        chunk=chunk or f"chunk {index}",
        bm25=bm25,
        document=document if document is not None else index + 1,
        page=page,
        section=section,
    )


def test_rrf_uses_default_formula_and_boosts_shared_chunk() -> None:
    """A chunk present in both rankings receives both reciprocal scores."""
    shared_vector = vector_result(0, chunk="shared", document=7, score=0.93)
    shared_keyword = keyword_result(0, chunk="shared", document=7, bm25=-2.4)
    keyword_first = keyword_result(1, chunk="keyword first", document=8)

    results = RRFService().fuse(
        [shared_vector],
        [keyword_first, shared_keyword],
    )

    assert RRF_DEFAULT_K == 60
    assert results[0].chunk == "shared"
    assert results[0].final_score == pytest.approx(1 / 61 + 1 / 62)
    assert results[0].sources == (
        RRFSourceScore(source="vector", original_score=0.93),
        RRFSourceScore(source="keyword", original_score=-2.4),
    )
    assert results[1].final_score == pytest.approx(1 / 61)


def test_rrf_returns_only_top8() -> None:
    """Fused output is sorted by final score and limited to eight chunks."""
    vectors = [vector_result(index) for index in range(12)]

    results = RRFService().fuse(vectors, [])

    assert len(results) == RRF_OUTPUT_LIMIT == 8
    assert [result.chunk for result in results] == [
        f"chunk {index}" for index in range(8)
    ]
    assert results[0].final_score > results[-1].final_score


def test_rrf_deduplicates_repeated_chunk_within_one_source() -> None:
    """A repeated source row contributes only its best original rank."""
    duplicate = vector_result(0, chunk="same", document=5, score=0.8)

    results = RRFService().fuse([duplicate, duplicate], [])

    assert len(results) == 1
    assert results[0].final_score == pytest.approx(1 / 61)
    assert results[0].sources == (RRFSourceScore(source="vector", original_score=0.8),)


def test_rrf_keeps_same_text_from_different_pages_separate() -> None:
    """Page metadata distinguishes otherwise identical document chunks."""
    first = vector_result(0, chunk="repeated", document=5, page=1)
    second = keyword_result(0, chunk="repeated", document=5, page=2)

    results = RRFService().fuse([first], [second])

    assert len(results) == 2
    assert {result.page for result in results} == {1, 2}


def test_rrf_ignores_candidates_beyond_each_top20_input() -> None:
    """Candidates beyond rank twenty do not contribute to fusion."""
    vectors = [vector_result(index) for index in range(21)]
    beyond_top20 = vectors[20]
    keyword = keyword_result(
        20,
        chunk=beyond_top20.chunk,
        document=beyond_top20.document,
    )

    results = RRFService().fuse(vectors, [keyword])
    matched = next(result for result in results if result.chunk == keyword.chunk)

    assert matched.sources == (
        RRFSourceScore(source="keyword", original_score=keyword.bm25),
    )
    assert matched.final_score == pytest.approx(1 / 61)


def test_rrf_supports_custom_positive_k() -> None:
    """A custom positive k value controls reciprocal rank contribution."""
    result = RRFService(k=10).fuse([vector_result(0)], [])[0]

    assert result.final_score == pytest.approx(1 / 11)
    with pytest.raises(ValueError, match="k must be positive"):
        RRFService(k=0)
