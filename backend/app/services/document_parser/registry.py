"""Document parser registration and selection."""

from pathlib import Path

from app.services.document_parser.base import Parser


class UnsupportedParserError(ValueError):
    """Raised when no parser is registered for a file extension."""


class ParserRegistry:
    """Map filename extensions to injected parser implementations."""

    def __init__(self) -> None:
        """Initialize an empty parser registry."""
        self._parsers: dict[str, Parser] = {}

    def register(self, extension: str, parser: Parser) -> None:
        """Register a parser for a case-insensitive filename extension."""
        normalized_extension = self._normalize_extension(extension)
        self._parsers[normalized_extension] = parser

    def get(self, file_path: Path) -> Parser:
        """Return the parser registered for a file path."""
        parser = self._parsers.get(file_path.suffix.lower())
        if parser is None:
            raise UnsupportedParserError
        return parser

    @staticmethod
    def _normalize_extension(extension: str) -> str:
        """Normalize an extension to lowercase with a leading dot."""
        normalized = extension.strip().lower()
        if not normalized:
            raise ValueError("extension must not be empty")
        return normalized if normalized.startswith(".") else f".{normalized}"
