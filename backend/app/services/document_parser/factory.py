"""Parser selection and unified document parsing interface."""

from pathlib import Path

from app.services.document_parser.base import Parser
from app.services.document_parser.docx import DocxParser
from app.services.document_parser.markdown import MarkdownParser
from app.services.document_parser.models import DocumentContent
from app.services.document_parser.pdf import PDFParser
from app.services.document_parser.txt import TxtParser


class UnsupportedFileTypeError(ValueError):
    """Raised when no parser supports a file extension."""


class ParserFactory:
    """Select a concrete document parser from a filename extension."""

    def __init__(self) -> None:
        """Initialize the supported parser mapping."""
        self._parsers: dict[str, Parser] = {
            ".pdf": PDFParser(),
            ".docx": DocxParser(),
            ".txt": TxtParser(),
            ".md": MarkdownParser(),
        }

    def get_parser(self, path: Path) -> Parser:
        """Return the parser matching a path's case-insensitive extension."""
        extension = path.suffix.lower()
        parser = self._parsers.get(extension)
        if parser is None:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {extension or '<none>'}"
            )
        return parser


class DocumentParser:
    """Expose one parsing interface for every supported document type."""

    def __init__(self, factory: ParserFactory | None = None) -> None:
        """Initialize the facade with a parser factory."""
        self._factory = factory or ParserFactory()

    def parse(self, path: Path) -> DocumentContent:
        """Parse a document using the parser selected from its extension."""
        return self._factory.get_parser(path).parse(path)
