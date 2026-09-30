"""Tests for ordered citation metadata construction."""

from app.schemas.search import SearchApiResult
from app.services.citation_builder import CITATION_LIMIT, Citation, CitationBuilder
from app.services.search import SearchServiceResult


def create_api_chunk(index: int) -> SearchApiResult:
    """Create a deterministic API search result."""
    return SearchApiResult(
        document=f"Document {index + 1}.pdf",
        page=index + 1,
        section=f"Section {index + 1}",
        content=f"Content {index + 1}",
        score=1.0 / (index + 1),
    )


def test_citation_builder_maps_api_result_fields() -> None:
    """An API search result maps to the required citation fields."""
    chunk = SearchApiResult(
        document="Cisco OSPF.pdf",
        page=12,
        section="Area",
        content="OSPF divides a network into areas.",
        score=0.93,
    )

    citations = CitationBuilder().build([chunk])

    assert citations == [
        Citation(
            id="S1",
            document="Cisco OSPF.pdf",
            page=12,
            section="Area",
            content="OSPF divides a network into areas.",
        )
    ]


def test_citation_builder_preserves_order_and_assigns_stable_ids() -> None:
    """Citation IDs follow input rank without sorting by score or metadata."""
    chunks = [create_api_chunk(2), create_api_chunk(0), create_api_chunk(1)]

    citations = CitationBuilder().build(chunks)

    assert [citation.id for citation in citations] == ["S1", "S2", "S3"]
    assert [citation.document for citation in citations] == [
        "Document 3.pdf",
        "Document 1.pdf",
        "Document 2.pdf",
    ]


def test_citation_builder_preserves_missing_metadata() -> None:
    """Nullable page and section metadata remain unavailable in output."""
    chunk = SearchApiResult(
        document="Notes.txt",
        page=None,
        section=None,
        content="Plain text",
        score=0.5,
    )

    citation = CitationBuilder().build([chunk])[0]

    assert citation.page is None
    assert citation.section is None


def test_citation_builder_limits_output_to_top8() -> None:
    """Only the first eight ranked chunks become citations."""
    citations = CitationBuilder().build(
        [create_api_chunk(index) for index in range(10)]
    )

    assert CITATION_LIMIT == 8
    assert len(citations) == 8
    assert citations[-1].id == "S8"
    assert citations[-1].content == "Content 8"


def test_citation_builder_returns_empty_list_for_empty_input() -> None:
    """An empty retrieval result produces no citations."""
    assert CitationBuilder().build([]) == []


def test_citation_builder_supports_internal_search_results() -> None:
    """Internal chunk text and document IDs map to public citation fields."""
    chunk = SearchServiceResult(
        document=42,
        page=3,
        section="Neighbors",
        chunk="OSPF neighbor state content",
        score=0.1,
    )

    citations = CitationBuilder().build([chunk])

    assert citations == [
        Citation(
            id="S1",
            document="42",
            page=3,
            section="Neighbors",
            content="OSPF neighbor state content",
        )
    ]
