"""Retrieval-augmented streaming response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import SearchResult


class ChatRequest(BaseModel):
    """Validated question submitted to grounded generation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    conversation_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=2000)


class CitationSource(BaseModel):
    """A numbered retrieval source available to the generated answer."""

    label: str
    document_id: int
    chunk_index: int
    content: str
    page: int | None = None
    section: str | None = None

    @classmethod
    def from_search_result(
        cls,
        result: SearchResult,
        index: int,
    ) -> "CitationSource":
        """Create a one-based citation source from a search result."""
        return cls(
            label=f"S{index}",
            document_id=result.document_id,
            chunk_index=result.chunk_index,
            content=result.content,
            page=result.page,
            section=result.section,
        )


class ChatStreamEvent(BaseModel):
    """Payload emitted in one server-sent event."""

    type: Literal["sources", "delta", "done"]
    content: str | None = None
    sources: list[CitationSource] | None = None
