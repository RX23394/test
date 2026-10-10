"""Resolve retrieval labels to database-backed source metadata."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.repositories.document import DocumentRepository
from app.schemas.search import SearchResult

logger = logging.getLogger(__name__)

CITATION_LIMIT = 8


@dataclass(frozen=True, slots=True)
class Citation:
    """One source citation exposed alongside a grounded answer."""

    id: str
    document: str
    page: int | None
    section: str | None
    content: str


class CitationResolutionError(RuntimeError):
    """Raised when database metadata cannot resolve every source label."""


class CitationResolver:
    """Build user-visible citations from retrieval rows and documents."""

    def __init__(self, document_repository: DocumentRepository) -> None:
        """Initialize the resolver with a document repository."""
        self._document_repository = document_repository

    def resolve(self, results: Sequence[SearchResult]) -> list[Citation]:
        """Resolve ordered Top8 results without using generated model text.

        A chunk whose document disappeared is skipped: an orphan vector must not
        make every question about that subject fail forever. The remaining
        citations keep the rank labels of the source list, so ``S3`` still points
        at the third prompt source even when ``S2`` was dropped.
        """
        limited_results = results[:CITATION_LIMIT]
        try:
            documents = self._document_repository.get_by_ids(
                [result.document_id for result in limited_results]
            )
        except Exception as exc:
            raise CitationResolutionError("Citation document lookup failed") from exc

        citations: list[Citation] = []
        for index, result in enumerate(limited_results, start=1):
            document = documents.get(result.document_id)
            if document is None:
                logger.warning(
                    "Skipping citation S%s for missing document %s",
                    index,
                    result.document_id,
                )
                continue
            citations.append(
                Citation(
                    id=f"S{index}",
                    document=document.original_filename,
                    page=result.page,
                    section=result.section,
                    content=result.content,
                )
            )
        return citations
