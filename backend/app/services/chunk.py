"""Heading-aware, paragraph-preferred document chunking."""

import re
from dataclasses import dataclass

from app.models.chunk import Chunk
from app.services.document_parser import DocumentContent, DocumentPage
from app.services.token_counter import (
    EMBEDDING_ENCODING_NAME,
    EMBEDDING_PASSAGE_OVERHEAD,
    TokenCounter,
    embedding_prefix_tokens,
)

DEFAULT_TARGET_TOKENS = 320
DEFAULT_OVERLAP_TOKENS = 48
# Chunk sizes are measured with the embedding model's own tokenizer. cl100k
# undercounts ASCII-dense text such as the "+-+-+" rules in RFC diagrams by up
# to five times, so chunks that fit a cl100k budget were still rejected by the
# encoder's 512-token window and aborted indexing.
DEFAULT_ENCODING_NAME = EMBEDDING_ENCODING_NAME
# The limits below are therefore expressed in embedding tokens, inside the
# encoder's 512-token window; the tail of an oversized chunk would otherwise be
# dropped by the tokenizer without any error.
MAX_CHUNK_TOKENS = 450
MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
WORD_PATTERN = re.compile(r"\s*\S+")
PARAGRAPH_BREAK_PATTERN = re.compile(r"(?:\r?\n)[ \t]*(?:\r?\n)")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？；…!?;.])")


@dataclass(frozen=True, slots=True)
class _Section:
    """Text section created from a Markdown heading boundary."""

    text: str
    page: int | None
    title: str | None


@dataclass(frozen=True, slots=True)
class _Word:
    """Indivisible word and its token and paragraph metadata."""

    text: str
    token_count: int
    starts_paragraph: bool


class ChunkService:
    """Split document pages near token targets without cutting words."""

    def __init__(
        self,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        encoding_name: str = DEFAULT_ENCODING_NAME,
        max_chunk_tokens: int = MAX_CHUNK_TOKENS,
        token_counter: TokenCounter | None = None,
    ) -> None:
        """Initialize token targets, overlap, and tokenizer encoding.

        ``token_counter`` overrides ``encoding_name``; tests inject a cheap
        counter so chunk windows stay deterministic without loading the encoder.
        """
        if target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if overlap_tokens < 0 or overlap_tokens >= target_tokens:
            raise ValueError(
                "overlap_tokens must be non-negative and less than target_tokens"
            )
        if max_chunk_tokens < target_tokens:
            raise ValueError("max_chunk_tokens must not be smaller than target_tokens")

        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens
        self._max_chunk_tokens = max_chunk_tokens
        self._token_counter = token_counter or TokenCounter(encoding_name)
        # Text tokens are counted straight from the tokenizer, so the encoder's
        # fixed per-passage cost is added exactly once, when a finished chunk is
        # measured. Word counts stay raw: adding the cost per word would inflate
        # a paragraph by roughly twice its word count and cut the window short.
        self._passage_overhead = (
            EMBEDDING_PASSAGE_OVERHEAD + embedding_prefix_tokens()
            if token_counter is None and encoding_name == EMBEDDING_ENCODING_NAME
            else 0
        )
        # Words and sentences are measured without the per-passage cost, so they
        # are compared against the hard limit with the cost already deducted.
        self._word_token_limit = max(1, self._max_chunk_tokens - self._passage_overhead)

    def _count(self, text: str) -> int:
        """Return the encoder token cost of one finished chunk."""
        return self._token_counter.count(text) + self._passage_overhead

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Return globally indexed chunks for one parsed document."""
        chunks: list[Chunk] = []
        for page in document.pages:
            for section in self._split_sections(page):
                chunks.extend(
                    self._split_section(
                        document.filename,
                        section,
                        first_index=len(chunks),
                    )
                )
        return chunks

    def _split_sections(self, page: DocumentPage) -> list[_Section]:
        """Prefer Markdown headings as hard section boundaries."""
        lines = page.text.splitlines(keepends=True)
        if not any(MARKDOWN_HEADING_PATTERN.match(line.strip()) for line in lines):
            text = page.text.strip()
            return (
                [_Section(text=text, page=page.page_number, title=None)] if text else []
            )

        sections: list[_Section] = []
        accumulated: list[str] = []
        current_title: str | None = None
        for line in lines:
            match = MARKDOWN_HEADING_PATTERN.match(line.strip())
            if match is not None:
                self._append_section(
                    sections,
                    accumulated,
                    page=page.page_number,
                    title=current_title,
                )
                accumulated = [line]
                current_title = match.group(2).strip()
            else:
                accumulated.append(line)
        self._append_section(
            sections,
            accumulated,
            page=page.page_number,
            title=current_title,
        )
        return sections

    @staticmethod
    def _append_section(
        sections: list[_Section],
        lines: list[str],
        *,
        page: int | None,
        title: str | None,
    ) -> None:
        """Append one non-empty heading section."""
        text = "".join(lines).strip()
        if text:
            sections.append(_Section(text=text, page=page, title=title))

    def _split_section(
        self,
        filename: str,
        section: _Section,
        *,
        first_index: int,
    ) -> list[Chunk]:
        """Split a section at paragraph or complete-word boundaries."""
        words = self._create_words(section.text)
        chunks: list[Chunk] = []
        start = 0
        previous_end = 0

        while start < len(words):
            end = self._find_window_end(words, start, previous_end)
            text = "".join(word.text for word in words[start:end]).strip()
            chunk_index = first_index + len(chunks)
            chunks.append(
                Chunk(
                    id=f"{filename}:{section.page}:{chunk_index}",
                    document_id=None,
                    page=section.page,
                    section=section.title,
                    chunk_index=chunk_index,
                    text=text,
                    token_count=self._count(text),
                )
            )
            if end == len(words):
                break
            previous_end = end
            start = self._find_overlap_start(words, start, end)

        return chunks

    def _create_words(self, text: str) -> list[_Word]:
        """Token-count complete words while retaining leading whitespace.

        A whitespace-free run such as a Chinese paragraph or a long URL is split
        at sentence boundaries, and then by token count, so no single word can
        force a chunk past the embedding limit.
        """
        words: list[_Word] = []
        for match in WORD_PATTERN.finditer(text):
            for piece in self._split_oversized_word(match.group()):
                words.append(
                    _Word(
                        text=piece,
                        token_count=self._token_counter.count(piece),
                        starts_paragraph=bool(PARAGRAPH_BREAK_PATTERN.search(piece)),
                    )
                )
        return words

    def _split_oversized_word(self, word: str) -> list[str]:
        """Return one or more pieces that each fit the hard chunk limit."""
        if self._token_counter.count(word) <= self._word_token_limit:
            return [word]

        pieces: list[str] = []
        for sentence in SENTENCE_BOUNDARY_PATTERN.split(word):
            if not sentence:
                continue
            if self._token_counter.count(sentence) <= self._word_token_limit:
                pieces.append(sentence)
            else:
                pieces.extend(self._split_by_token_budget(sentence))
        return pieces or [word]

    def _split_by_token_budget(self, text: str) -> list[str]:
        """Split text without punctuation into pieces within the hard limit."""
        pieces: list[str] = []
        start = 0
        while start < len(text):
            end = self._largest_fitting_prefix(text, start)
            pieces.append(text[start:end])
            start = end
        return pieces

    def _largest_fitting_prefix(self, text: str, start: int) -> int:
        """Return the longest end offset whose piece fits the hard limit."""
        low = start + 1
        high = len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self._token_counter.count(text[start:middle]) <= self._word_token_limit:
                low = middle
            else:
                high = middle - 1
        return low

    def _find_window_end(
        self,
        words: list[_Word],
        start: int,
        previous_end: int,
    ) -> int:
        """Choose a target-sized end, preferring the latest paragraph end."""
        token_count = 0
        end = start
        preferred_end: int | None = None
        while end < len(words):
            next_count = token_count + words[end].token_count
            if end > start and next_count > self._target_tokens:
                break
            if words[end].starts_paragraph and end > start and end > previous_end:
                preferred_end = end
            token_count = next_count
            end += 1

        if end == len(words):
            return end
        if preferred_end is not None:
            return preferred_end
        if end <= previous_end:
            return min(len(words), previous_end + 1)
        return end

    def _find_overlap_start(
        self,
        words: list[_Word],
        window_start: int,
        window_end: int,
    ) -> int:
        """Return a complete-word overlap start near the configured size."""
        if self._overlap_tokens == 0:
            return window_end
        start = window_end
        token_count = 0
        while start > window_start and token_count < self._overlap_tokens:
            start -= 1
            token_count += words[start].token_count
        return window_end if start == window_start else start
