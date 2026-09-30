"""Tests for heading-aware, word-safe document chunking."""

import pytest
import tiktoken

from app.models.chunk import Chunk
from app.services.chunk import ChunkService
from app.services.document_parser import DocumentContent, DocumentPage


def create_content(
    text: str,
    *,
    page_number: int = 1,
    filename: str = "document.md",
) -> DocumentContent:
    """Create one-page document content for chunking tests."""
    return DocumentContent(
        filename=filename,
        pages=[DocumentPage(page_number=page_number, text=text)],
    )


def test_chunk_service_prefers_markdown_heading_boundaries() -> None:
    """Markdown headings create separate chunks and section metadata."""
    document = create_content(
        "# Introduction\nIntro text.\n# Routing\nRouting text.",
        page_number=2,
    )

    chunks = ChunkService().create_chunks(document)

    assert [chunk.text for chunk in chunks] == [
        "# Introduction\nIntro text.",
        "# Routing\nRouting text.",
    ]
    assert [chunk.section for chunk in chunks] == ["Introduction", "Routing"]


def test_chunk_service_prefers_natural_paragraph_boundaries() -> None:
    """Untitled content is packed to target size at paragraph boundaries."""
    document = create_content(
        "alpha beta gamma delta\n\n" "one two three four\n\n" "red blue green yellow"
    )

    chunks = ChunkService(target_tokens=12, overlap_tokens=0).create_chunks(document)

    assert [chunk.text for chunk in chunks] == [
        "alpha beta gamma delta\n\none two three four",
        "red blue green yellow",
    ]
    assert all(chunk.section is None for chunk in chunks)


def test_chunk_service_uses_complete_word_overlap() -> None:
    """Overlap meets the token target using only complete source words."""
    encoding = tiktoken.get_encoding("cl100k_base")
    source_words = [f"word{index}" for index in range(30)]
    document = create_content(" ".join(source_words))

    chunks = ChunkService(target_tokens=12, overlap_tokens=3).create_chunks(document)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 12 for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        previous_words = previous.text.split()
        current_words = current.text.split()
        overlap_size = 0
        for size in range(1, min(len(previous_words), len(current_words)) + 1):
            if previous_words[-size:] == current_words[:size]:
                overlap_size = size
        assert overlap_size > 0
        overlap_text = " ".join(current_words[:overlap_size])
        assert len(encoding.encode(overlap_text)) >= 3


def test_chunk_service_defaults_to_about_500_tokens_with_80_overlap() -> None:
    """Default chunks target 500 tokens and overlap by complete words."""
    encoding = tiktoken.get_encoding("cl100k_base")
    document = create_content(" ".join(f"token{index}" for index in range(500)))

    chunks = ChunkService().create_chunks(document)

    assert len(chunks) > 1
    assert chunks[0].token_count == 500
    previous_words = chunks[0].text.split()
    current_words = chunks[1].text.split()
    overlap_size = 0
    for size in range(1, min(len(previous_words), len(current_words)) + 1):
        if previous_words[-size:] == current_words[:size]:
            overlap_size = size
    assert overlap_size > 0
    overlap_text = " ".join(current_words[:overlap_size])
    assert len(encoding.encode(overlap_text)) >= 80


def test_chunk_service_never_truncates_words() -> None:
    """Long paragraphs are windowed only between complete source words."""
    source_words = [f"extraordinaryword{index}" for index in range(25)]
    chunks = ChunkService(target_tokens=20, overlap_tokens=4).create_chunks(
        create_content(" ".join(source_words))
    )

    emitted_words = {word for chunk in chunks for word in chunk.text.split()}

    assert emitted_words == set(source_words)
    assert all(word in source_words for word in emitted_words)


def test_chunk_service_preserves_page_section_and_indexes() -> None:
    """Chunks retain page and section with global sequential indexes."""
    document = DocumentContent(
        filename="pages.md",
        pages=[
            DocumentPage(page_number=1, text="# Intro\nPage one"),
            DocumentPage(page_number=2, text="# Details\nPage two"),
        ],
    )

    chunks = ChunkService().create_chunks(document)

    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert [(chunk.page, chunk.section, chunk.chunk_index) for chunk in chunks] == [
        (1, "Intro", 0),
        (2, "Details", 1),
    ]
    assert [chunk.id for chunk in chunks] == ["pages.md:1:0", "pages.md:2:1"]
    assert all(chunk.document_id is None for chunk in chunks)


def test_chunk_service_returns_no_chunks_for_blank_content() -> None:
    """Blank document content does not create an empty chunk."""
    chunks = ChunkService().create_chunks(create_content(" \n\t"))

    assert chunks == []


@pytest.mark.parametrize(
    ("target_tokens", "overlap_tokens"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_chunk_service_rejects_invalid_window_configuration(
    target_tokens: int,
    overlap_tokens: int,
) -> None:
    """Invalid target and overlap values are rejected."""
    with pytest.raises(ValueError):
        ChunkService(
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
