"""Heading-aware, paragraph-preferred document chunking."""

import re
from dataclasses import dataclass

from app.models.chunk import Chunk
from app.services.document_parser import DocumentContent, DocumentPage
from app.services.token_counter import TokenCounter

DEFAULT_TARGET_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 80
DEFAULT_ENCODING_NAME = "cl100k_base"
MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
WORD_PATTERN = re.compile(r"\s*\S+")
PARAGRAPH_BREAK_PATTERN = re.compile(r"(?:\r?\n)[ \t]*(?:\r?\n)")


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
    ) -> None:
        """Initialize token targets, overlap, and tokenizer encoding."""
        if target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if overlap_tokens < 0 or overlap_tokens >= target_tokens:
            raise ValueError(
                "overlap_tokens must be non-negative and less than target_tokens"
            )

        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens
        self._token_counter = TokenCounter(encoding_name)

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
                    token_count=self._token_counter.count(text),
                )
            )
            if end == len(words):
                break
            previous_end = end
            start = self._find_overlap_start(words, start, end)

        return chunks

    def _create_words(self, text: str) -> list[_Word]:
        """Token-count complete words while retaining leading whitespace."""
        return [
            _Word(
                text=match.group(),
                token_count=self._token_counter.count(match.group()),
                starts_paragraph=bool(PARAGRAPH_BREAK_PATTERN.search(match.group())),
            )
            for match in WORD_PATTERN.finditer(text)
        ]

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
