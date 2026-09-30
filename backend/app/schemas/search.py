"""Hybrid retrieval schemas."""

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    """Validated text submitted to hybrid retrieval."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=1000)


class RetrievalCandidate(BaseModel):
    """One ranked chunk returned by an individual retriever."""

    document_id: int
    chunk_index: int
    content: str
    page: int | None = None
    section: str | None = None
    score: float


class SearchResult(BaseModel):
    """One reciprocal-rank-fused retrieval result."""

    document_id: int
    chunk_index: int
    content: str
    page: int | None = None
    section: str | None = None
    score: float = Field(gt=0)


class SearchApiResult(BaseModel):
    """One retrieval-only result returned by the search API."""

    document: str
    page: int | None = None
    section: str | None = None
    content: str
    score: float = Field(gt=0)
