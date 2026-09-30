"""Tests for parser selection and the unified parsing facade."""

from pathlib import Path

import pytest

from app.services.document_parser import (
    DocumentContent,
    DocumentPage,
    DocumentParser,
    DocxParser,
    MarkdownParser,
    ParserFactory,
    PDFParser,
    TxtParser,
    UnsupportedFileTypeError,
)


@pytest.mark.parametrize(
    ("filename", "parser_type"),
    [
        ("guide.pdf", PDFParser),
        ("guide.docx", DocxParser),
        ("guide.txt", TxtParser),
        ("guide.md", MarkdownParser),
    ],
)
def test_parser_factory_returns_parser_by_extension(
    filename: str,
    parser_type: type[PDFParser | DocxParser | TxtParser | MarkdownParser],
) -> None:
    """Each supported extension resolves to its concrete parser."""
    parser = ParserFactory().get_parser(Path(filename))

    assert isinstance(parser, parser_type)


def test_parser_factory_is_case_insensitive() -> None:
    """Uppercase extensions resolve through the normalized mapping."""
    parser = ParserFactory().get_parser(Path("GUIDE.PDF"))

    assert isinstance(parser, PDFParser)


@pytest.mark.parametrize("filename", ["guide.csv", "README", "guide.markdown"])
def test_parser_factory_rejects_unknown_extensions(filename: str) -> None:
    """Unsupported and missing extensions raise the public factory error."""
    with pytest.raises(UnsupportedFileTypeError):
        ParserFactory().get_parser(Path(filename))


def test_document_parser_exposes_unified_parse_interface(tmp_path: Path) -> None:
    """The facade selects a parser and returns unified document content."""
    path = tmp_path / "guide.txt"
    path.write_text("Network guide", encoding="utf-8")

    result = DocumentParser().parse(path)

    assert result == DocumentContent(
        filename="guide.txt",
        pages=[DocumentPage(page_number=1, text="Network guide")],
    )


def test_document_parser_rejects_unknown_file_type(tmp_path: Path) -> None:
    """The unified facade propagates the public unsupported-type error."""
    path = tmp_path / "guide.csv"

    with pytest.raises(UnsupportedFileTypeError):
        DocumentParser().parse(path)
