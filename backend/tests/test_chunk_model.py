"""Tests for the database-independent Chunk dataclass."""

from dataclasses import asdict, fields, is_dataclass

from app.models.chunk import Chunk


def test_chunk_is_dataclass_with_required_fields() -> None:
    """Chunk is a dataclass exposing exactly the requested fields."""
    assert is_dataclass(Chunk)
    assert [field.name for field in fields(Chunk)] == [
        "id",
        "document_id",
        "page",
        "section",
        "chunk_index",
        "text",
        "token_count",
    ]


def test_chunk_stores_text_and_source_metadata() -> None:
    """Chunk values remain available without persistence or vector state."""
    chunk = Chunk(
        id="document-7-chunk-2",
        document_id=7,
        page=3,
        section="Routing",
        chunk_index=2,
        text="OSPF is a link-state routing protocol.",
        token_count=9,
    )

    assert asdict(chunk) == {
        "id": "document-7-chunk-2",
        "document_id": 7,
        "page": 3,
        "section": "Routing",
        "chunk_index": 2,
        "text": "OSPF is a link-state routing protocol.",
        "token_count": 9,
    }


def test_chunk_accepts_missing_page_and_section() -> None:
    """Page and section metadata may be unavailable for plain text."""
    chunk = Chunk(
        id="document-8-chunk-0",
        document_id=8,
        page=None,
        section=None,
        chunk_index=0,
        text="Unsectioned text",
        token_count=4,
    )

    assert chunk.page is None
    assert chunk.section is None
