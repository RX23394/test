"""Stable citation metadata construction for retrieved chunks."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.search import SearchApiResult
from app.services.search import SearchServiceResult

CITATION_LIMIT = 8


@dataclass(frozen=True, slots=True)
class Citation:
    """One source citation exposed alongside a grounded answer."""

    id: str
    document: str
    page: int | None
    section: str | None
    content: str


class CitationBuilder:
    """Convert ranked search chunks into ordered source citations."""

    def build(
        self,
        chunks: Sequence[SearchApiResult | SearchServiceResult],
    ) -> list[Citation]:
        """Return at most eight citations in the input ranking order."""
        citations: list[Citation] = []
        for index, chunk in enumerate(chunks[:CITATION_LIMIT], start=1):
            content = (
                chunk.content if isinstance(chunk, SearchApiResult) else chunk.chunk
            )
            citations.append(
                Citation(
                    id=f"S{index}",
                    document=str(chunk.document),
                    page=chunk.page,
                    section=chunk.section,
                    content=content,
                )
            )
        return citations
