"""Document parsing and chunking orchestration."""

from pathlib import Path
from typing import Protocol

from app.models.chunk import Chunk
from app.services.chunk import ChunkService
from app.services.document_parser import DocumentContent, DocumentParser


class ContentParser(Protocol):
    """Document parser contract required by the orchestration service."""

    def parse(self, path: Path) -> DocumentContent:
        """Parse one uploaded document path into normalized content."""
        ...


class ContentChunker(Protocol):
    """Chunking contract required by the orchestration service."""

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Split normalized document content into text chunks."""
        ...


class DocumentParseResult:
    """Document parse result containing chunk count and chunk details."""

    def __init__(self, chunks: list[Chunk]) -> None:
        """Initialize a result from the generated chunk list."""
        self.chunk_count = len(chunks)
        self.chunks = chunks

    chunk_count: int
    chunks: list[Chunk]


class DocumentParseService:
    """Parse an uploaded file and split its content into text chunks."""

    def __init__(
        self,
        parser: ContentParser | None = None,
        chunk_service: ContentChunker | None = None,
    ) -> None:
        """Initialize parser and chunking dependencies."""
        self._parser = parser if parser is not None else DocumentParser()
        self._chunk_service = (
            chunk_service if chunk_service is not None else ChunkService()
        )

    def parse(self, path: Path) -> DocumentParseResult:
        """Parse an uploaded path and return its generated chunk details."""
        content = self._parser.parse(path)
        chunks = self._chunk_service.create_chunks(content)
        return DocumentParseResult(chunks)
