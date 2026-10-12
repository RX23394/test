"""Tests for heading-aware, word-safe document chunking."""

import pytest
import tiktoken

from app.models.chunk import Chunk
from app.services import chunk, token_counter
from app.services.chunk import (
    DEFAULT_OVERLAP_TOKENS,
    DEFAULT_TARGET_TOKENS,
    MAX_CHUNK_TOKENS,
    ChunkService,
)
from app.services.document_parser import DocumentContent, DocumentPage
from app.services.token_counter import TokenCounter


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


def create_service(**kwargs: object) -> ChunkService:
    """Create a chunker whose windows are measured with a cheap tokenizer.

    The production default measures with the embedding model's tokenizer, which
    needs the model assets; window arithmetic is independent of that choice, so
    unit tests pin cl100k for deterministic expectations.
    """
    kwargs.setdefault("token_counter", TokenCounter("cl100k_base"))
    return ChunkService(**kwargs)  # type: ignore[arg-type]


def test_chunk_service_prefers_markdown_heading_boundaries() -> None:
    """Markdown headings create separate chunks and section metadata."""
    document = create_content(
        "# Introduction\nIntro text.\n# Routing\nRouting text.",
        page_number=2,
    )

    chunks = create_service().create_chunks(document)

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

    chunks = create_service(target_tokens=12, overlap_tokens=0).create_chunks(document)

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

    chunks = create_service(target_tokens=12, overlap_tokens=3).create_chunks(document)

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


def test_chunk_service_defaults_to_about_320_tokens_with_48_overlap() -> None:
    """Default chunks target 320 tokens and overlap by complete words."""
    encoding = tiktoken.get_encoding("cl100k_base")
    document = create_content(" ".join(f"token{index}" for index in range(500)))

    chunks = create_service().create_chunks(document)

    assert len(chunks) > 1
    assert all(chunk.token_count <= DEFAULT_TARGET_TOKENS for chunk in chunks)
    assert chunks[0].token_count > DEFAULT_OVERLAP_TOKENS
    previous_words = chunks[0].text.split()
    current_words = chunks[1].text.split()
    overlap_size = 0
    for size in range(1, min(len(previous_words), len(current_words)) + 1):
        if previous_words[-size:] == current_words[:size]:
            overlap_size = size
    assert overlap_size > 0
    overlap_text = " ".join(current_words[:overlap_size])
    assert len(encoding.encode(overlap_text)) >= DEFAULT_OVERLAP_TOKENS


def test_chunk_service_sizes_chunks_with_the_embedding_tokenizer() -> None:
    """Chunk limits are measured with the encoder that will embed them.

    ASCII diagrams are the regression case: cl100k counts a "+-+-+-+-+-+" rule
    as a single token while the embedding tokenizer spends several per rule, so
    a chunk that fit the cl100k budget used to overflow the 512-token encoder
    window and abort indexing with ``EmbeddingInputTooLongError``.
    """
    rule = "+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+"
    diagram = "\n".join(
        [
            "Header Format",
            "",
            rule,
            "|Version| Traffic Class |           Flow Label                  |",
            rule,
            "|         Payload Length        |  Next Header  |   Hop Limit   |",
            rule,
        ]
        * 4
    )

    chunks = ChunkService().create_chunks(create_content(diagram))

    assert len(chunks) > 1
    assert all(0 < chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_chunk_service_counts_the_passage_overhead_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The encoder's per-passage cost is charged once, not once per word.

    Charging it per word inflated a 50-word paragraph by 200 tokens, which cut
    the window to a fraction of its target and multiplied the chunk count.
    """

    class WordTokenizer:
        """Count one token per whitespace-separated word."""

        def __call__(self, text: str, **_: object) -> dict[str, list[int]]:
            return {"input_ids": list(range(len(text.split())))}

    class WordEncoding:
        """Count one token per whitespace-separated word, as the encoder would."""

        def encode(self, text: str) -> list[int]:
            """Return one token id per word."""
            return list(range(len(text.split())))

    # Patch in each module's own namespace: both import the constant directly.
    monkeypatch.setattr(token_counter, "EMBEDDING_PASSAGE_OVERHEAD", 0)
    monkeypatch.setattr(chunk, "EMBEDDING_PASSAGE_OVERHEAD", 0)
    monkeypatch.setattr(
        token_counter,
        "_load_embedding_encoding",
        lambda: WordEncoding(),
    )

    words = " ".join(f"word{index}" for index in range(20))
    # No injected counter: this test measures the embedding backend itself.
    chunks = ChunkService(
        target_tokens=10,
        overlap_tokens=0,
        max_chunk_tokens=10,
    ).create_chunks(create_content(words))

    # 20 single-token words at a target of 10 must produce exactly two chunks.
    # A per-word passage overhead would have split them into many more, and the
    # special-token pair would have shrunk the window further.
    assert len(chunks) == 2
    assert [chunk.text.split() for chunk in chunks] == [
        [f"word{index}" for index in range(10)],
        [f"word{index}" for index in range(10, 20)],
    ]


def test_chunk_service_splits_a_long_unbroken_chinese_paragraph() -> None:
    """A whitespace-free CJK paragraph stays inside the embedding limit."""
    sentences = "配置BGP邻居关系时需要指定对端自治系统号。"
    document = create_content(sentences * 200)

    chunks = ChunkService().create_chunks(document)

    assert len(chunks) > 1
    assert all(0 < chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)
    for sentence in {sentences}:
        assert any(sentence in chunk.text for chunk in chunks)


def test_chunk_service_hard_splits_a_single_oversized_sentence() -> None:
    """One sentence without punctuation is split by token count, not dropped."""
    document = create_content("配置BGP邻居关系时需要指定对端自治系统号" * 100)

    chunks = ChunkService().create_chunks(document)

    assert len(chunks) > 1
    assert all(0 < chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_chunk_service_rejects_a_hard_limit_below_the_target() -> None:
    """A hard limit smaller than the target window is rejected."""
    with pytest.raises(ValueError, match="max_chunk_tokens"):
        ChunkService(target_tokens=100, overlap_tokens=10, max_chunk_tokens=50)


def test_chunk_service_never_truncates_words() -> None:
    """Long paragraphs are windowed only between complete source words."""
    source_words = [f"extraordinaryword{index}" for index in range(25)]
    chunks = create_service(target_tokens=20, overlap_tokens=4).create_chunks(
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
