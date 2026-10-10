"""Reciprocal-rank-fused vector and full-text retrieval."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.schemas.search import RetrievalCandidate, SearchResult
from app.services.keyword_search import KeywordSearchResult
from app.services.rrf import RRFResult, RRFService
from app.services.vector_search import VectorSearchResult

logger = logging.getLogger(__name__)

VECTOR_SEARCH_LIMIT = 30
FTS_SEARCH_LIMIT = 20
HYBRID_RESULT_LIMIT = 8
RRF_K = 60


class QueryEmbeddingProvider(Protocol):
    """Query-vector capability required by hybrid retrieval."""

    def embed_query(self, query: str) -> list[list[float]]:
        """Return the vector representation of a retrieval query."""
        ...


class VectorSearchRepository(Protocol):
    """Vector candidate retrieval contract."""

    def search(
        self,
        vector: Sequence[float],
        limit: int,
    ) -> list[RetrievalCandidate]:
        """Return vector-ranked retrieval candidates."""
        ...


class TextSearchRepository(Protocol):
    """Full-text candidate retrieval contract."""

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        """Return text-ranked retrieval candidates."""
        ...


class HybridSearchError(RuntimeError):
    """Raised when a hybrid retrieval dependency fails."""


class HybridSearchService:
    """Fuse vector and FTS5 ranks with reciprocal rank fusion."""

    def __init__(
        self,
        embedding_provider: QueryEmbeddingProvider,
        vector_repository: VectorSearchRepository,
        text_repository: TextSearchRepository,
        *,
        min_vector_score: float = 0.0,
    ) -> None:
        """Initialize hybrid retrieval dependencies and the relevance floor.

        ``min_vector_score`` is the second relevance gate: the repository also
        applies its own threshold, but RRF can still promote a weak vector match
        when it also appears in the keyword list, so candidates are re-checked
        here before fusion.
        """
        self._embedding_provider = embedding_provider
        self._vector_repository = vector_repository
        self._text_repository = text_repository
        self._min_vector_score = min_vector_score

    def search(self, query: str) -> list[SearchResult]:
        """Retrieve Top30 vector and Top20 keyword candidates, then return Top8."""
        try:
            query_vectors = self._embedding_provider.embed_query(query)
            vector_candidates = [
                candidate
                for candidate in self._vector_repository.search(
                    query_vectors[0],
                    VECTOR_SEARCH_LIMIT,
                )
                if candidate.score >= self._min_vector_score
            ]
            text_candidates = self._text_repository.search(
                query,
                FTS_SEARCH_LIMIT,
            )
            return self._fuse(vector_candidates, text_candidates)
        except Exception as exc:
            logger.exception("Hybrid retrieval failed")
            raise HybridSearchError from exc

    @staticmethod
    def _fuse(
        vector_candidates: Sequence[RetrievalCandidate],
        text_candidates: Sequence[RetrievalCandidate],
    ) -> list[SearchResult]:
        """Fuse candidate ranks by document and chunk identity."""
        candidates: dict[tuple[int, int], RetrievalCandidate] = {}
        scores: dict[tuple[int, int], float] = {}

        for ranked_candidates in (vector_candidates, text_candidates):
            for rank, candidate in enumerate(ranked_candidates, start=1):
                key = (candidate.document_id, candidate.chunk_index)
                candidates.setdefault(key, candidate)
                scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)

        ranked_keys = sorted(
            scores,
            key=lambda key: (-scores[key], key[0], key[1]),
        )[:HYBRID_RESULT_LIMIT]
        return [
            SearchResult(
                document_id=candidates[key].document_id,
                chunk_index=candidates[key].chunk_index,
                content=candidates[key].content,
                page=candidates[key].page,
                section=candidates[key].section,
                score=scores[key],
            )
            for key in ranked_keys
        ]


class VectorQuestionSearch(Protocol):
    """Question-to-vector search contract used by SearchService."""

    def search(self, question: str) -> list[VectorSearchResult]:
        """Return vector-ranked chunks for a question."""
        ...


class KeywordQuestionSearch(Protocol):
    """Question-to-keyword search contract used by SearchService."""

    def search(self, question: str) -> list[KeywordSearchResult]:
        """Return BM25-ranked chunks for a question."""
        ...


class RankFusion(Protocol):
    """Vector and keyword rank fusion contract."""

    def fuse(
        self,
        vector_results: Sequence[VectorSearchResult],
        keyword_results: Sequence[KeywordSearchResult],
    ) -> list[RRFResult]:
        """Return deduplicated fused results."""
        ...


@dataclass(frozen=True, slots=True)
class SearchServiceResult:
    """One final Top8 chunk returned to the search caller."""

    document: int
    page: int | None
    section: str | None
    chunk: str
    score: float


class SearchService:
    """Run vector and keyword retrieval followed by RRF Top8 fusion."""

    def __init__(
        self,
        vector_search_service: VectorQuestionSearch,
        keyword_search_service: KeywordQuestionSearch,
        rrf_service: RankFusion | None = None,
        *,
        min_vector_score: float = 0.0,
    ) -> None:
        """Initialize both retrievers, fusion, and the relevance floor."""
        self._vector_search_service = vector_search_service
        self._keyword_search_service = keyword_search_service
        self._rrf_service = rrf_service if rrf_service is not None else RRFService()
        self._min_vector_score = min_vector_score

    def search(self, question: str) -> list[SearchServiceResult]:
        """Retrieve, fuse, and return at most eight chunks for a question."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        vector_results = [
            result
            for result in self._vector_search_service.search(normalized_question)
            if result.score >= self._min_vector_score
        ]
        keyword_results = self._keyword_search_service.search(normalized_question)
        fused_results = self._rrf_service.fuse(vector_results, keyword_results)
        return [
            SearchServiceResult(
                document=result.document,
                page=result.page,
                section=result.section,
                chunk=result.chunk,
                score=result.final_score,
            )
            for result in fused_results[:8]
        ]
