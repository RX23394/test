"""Tests for document parsing and chunking orchestration."""

from pathlib import Path

from app.models.chunk import Chunk
from app.services.document_parse import DocumentParseResult, DocumentParseService
from app.services.document_parser import DocumentContent, DocumentPage
from app.services.token_counter import TokenCounter


class FakeParser:
    """Record the uploaded path and return deterministic document content."""

    def __init__(self, content: DocumentContent) -> None:
        """Initialize the fake parser result."""
        self.content = content
        self.received_path: Path | None = None

    def parse(self, path: Path) -> DocumentContent:
        """Record and return normalized content."""
        self.received_path = path
        return self.content


class FakeChunkService:
    """Record document content and return deterministic chunks."""

    def __init__(self, chunks: list[Chunk]) -> None:
        """Initialize the fake chunk result."""
        self.chunks = chunks
        self.received_content: DocumentContent | None = None

    def create_chunks(self, document: DocumentContent) -> list[Chunk]:
        """Record normalized content and return chunks."""
        self.received_content = document
        return self.chunks


def test_document_parse_service_runs_parser_then_chunk_service() -> None:
    """The service passes parser output directly into the chunk service."""
    path = Path("uploaded/guide.md")
    content = DocumentContent(
        filename="guide.md",
        pages=[DocumentPage(page_number=1, text="# Routing\nOSPF details")],
    )
    chunks = [
        Chunk(
            id="guide.md:1:0",
            document_id=None,
            page=1,
            section="Routing",
            chunk_index=0,
            text="# Routing\nOSPF details",
            token_count=6,
        )
    ]
    parser = FakeParser(content)
    chunk_service = FakeChunkService(chunks)

    result = DocumentParseService(parser, chunk_service).parse(path)

    assert parser.received_path == path
    assert chunk_service.received_content is content
    assert result.chunk_count == 1
    assert result.chunks is chunks


def test_document_parse_service_returns_requested_chunk_details(
    tmp_path: Path,
) -> None:
    """The real pipeline returns content, page, section, and token count."""
    path = tmp_path / "network.md"
    path.write_text(
        "# Routing\nOSPF details.\n\n# Switching\nVLAN details.",
        encoding="utf-8",
    )

    result = DocumentParseService().parse(path)

    assert isinstance(result, DocumentParseResult)
    assert result.chunk_count == 2
    assert [chunk.text for chunk in result.chunks] == [
        "# Routing\nOSPF details.",
        "# Switching\nVLAN details.",
    ]
    assert [chunk.page for chunk in result.chunks] == [1, 1]
    assert [chunk.section for chunk in result.chunks] == ["Routing", "Switching"]
    counter = TokenCounter()
    assert [chunk.token_count for chunk in result.chunks] == [
        counter.count(chunk.text) for chunk in result.chunks
    ]


def test_document_parse_service_returns_empty_result_for_blank_file(
    tmp_path: Path,
) -> None:
    """A blank uploaded text file produces a zero-count chunk result."""
    path = tmp_path / "blank.txt"
    path.write_text("", encoding="utf-8")

    result = DocumentParseService().parse(path)

    assert result.chunk_count == 0
    assert result.chunks == []
