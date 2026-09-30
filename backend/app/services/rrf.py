"""Reciprocal Rank Fusion for vector and keyword results."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.services.keyword_search import KeywordSearchResult
from app.services.vector_search import VectorSearchResult

RRF_DEFAULT_K = 60
RRF_INPUT_LIMIT = 20
RRF_OUTPUT_LIMIT = 8
SearchSource = Literal["vector", "keyword"]
ChunkKey = tuple[int, int | None, str | None, str]


@dataclass(frozen=True, slots=True)
class RRFSourceScore:
    """One retrieval source and its unchanged original score."""

    source: SearchSource
    original_score: float


@dataclass(frozen=True, slots=True)
class RRFResult:
    """One deduplicated chunk with source and fused score details."""

    chunk: str
    document: int
    page: int | None
    section: str | None
    sources: tuple[RRFSourceScore, ...]
    final_score: float


@dataclass(slots=True)
class _Accumulator:
    """Mutable score state for one deduplicated chunk."""

    chunk: str
    document: int
    page: int | None
    section: str | None
    first_seen: int
    sources: list[RRFSourceScore] = field(default_factory=list)
    final_score: float = 0.0


class RRFService:
    """Fuse vector and keyword rankings with reciprocal rank fusion."""

    def __init__(self, k: int = RRF_DEFAULT_K) -> None:
        """Initialize the positive RRF rank constant."""
        if k <= 0:
            raise ValueError("k must be positive")
        self._k = k

    def fuse(
        self,
        vector_results: Sequence[VectorSearchResult],
        keyword_results: Sequence[KeywordSearchResult],
    ) -> list[RRFResult]:
        """Deduplicate two Top20 rankings and return fused Top8 results."""
        accumulators: dict[ChunkKey, _Accumulator] = {}
        self._add_vector_results(accumulators, vector_results)
        self._add_keyword_results(accumulators, keyword_results)
        ranked = sorted(
            accumulators.values(),
            key=lambda item: (-item.final_score, item.first_seen),
        )[:RRF_OUTPUT_LIMIT]
        return [
            RRFResult(
                chunk=item.chunk,
                document=item.document,
                page=item.page,
                section=item.section,
                sources=tuple(item.sources),
                final_score=item.final_score,
            )
            for item in ranked
        ]

    def _add_vector_results(
        self,
        accumulators: dict[ChunkKey, _Accumulator],
        results: Sequence[VectorSearchResult],
    ) -> None:
        """Add unique vector ranks and preserve cosine scores."""
        seen: set[ChunkKey] = set()
        for rank, result in enumerate(results[:RRF_INPUT_LIMIT], start=1):
            key = self._key(
                result.document,
                result.page,
                result.section,
                result.chunk,
            )
            if key in seen:
                continue
            seen.add(key)
            item = self._get_or_create(
                accumulators,
                key,
                result.chunk,
                result.document,
                result.page,
                result.section,
            )
            item.sources.append(
                RRFSourceScore(source="vector", original_score=result.score)
            )
            item.final_score += 1.0 / (self._k + rank)

    def _add_keyword_results(
        self,
        accumulators: dict[ChunkKey, _Accumulator],
        results: Sequence[KeywordSearchResult],
    ) -> None:
        """Add unique keyword ranks and preserve BM25 scores."""
        seen: set[ChunkKey] = set()
        for rank, result in enumerate(results[:RRF_INPUT_LIMIT], start=1):
            key = self._key(
                result.document,
                result.page,
                result.section,
                result.chunk,
            )
            if key in seen:
                continue
            seen.add(key)
            item = self._get_or_create(
                accumulators,
                key,
                result.chunk,
                result.document,
                result.page,
                result.section,
            )
            item.sources.append(
                RRFSourceScore(source="keyword", original_score=result.bm25)
            )
            item.final_score += 1.0 / (self._k + rank)

    @staticmethod
    def _key(
        document: int,
        page: int | None,
        section: str | None,
        chunk: str,
    ) -> ChunkKey:
        """Return the complete identity used to deduplicate a chunk."""
        return document, page, section, chunk

    @staticmethod
    def _get_or_create(
        accumulators: dict[ChunkKey, _Accumulator],
        key: ChunkKey,
        chunk: str,
        document: int,
        page: int | None,
        section: str | None,
    ) -> _Accumulator:
        """Return existing score state or create it in first-seen order."""
        item = accumulators.get(key)
        if item is None:
            item = _Accumulator(
                chunk=chunk,
                document=document,
                page=page,
                section=section,
                first_seen=len(accumulators),
            )
            accumulators[key] = item
        return item
