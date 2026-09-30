"""Tests for the text-only PyMuPDF parser."""

from pathlib import Path

import fitz

from app.services.document_parser import DocumentContent, DocumentPage, PDFParser
from app.services.document_parser.dependencies import get_parser_registry


def create_pdf(path: Path, page_texts: list[str | None]) -> None:
    """Create a PDF whose pages optionally contain selectable text."""
    with fitz.open() as document:
        for text in page_texts:
            page = document.new_page()
            if text is not None:
                page.insert_text((72, 72), text)
        document.save(path)


def test_pdf_parser_reads_text_by_page(tmp_path: Path) -> None:
    """Text is extracted per page with original one-based page numbers."""
    path = tmp_path / "network-guide.pdf"
    create_pdf(path, ["First page", "Second page"])

    result = PDFParser().parse(path)

    assert result == DocumentContent(
        filename="network-guide.pdf",
        pages=[
            DocumentPage(page_number=1, text="First page"),
            DocumentPage(page_number=2, text="Second page"),
        ],
    )


def test_pdf_parser_skips_empty_pages(tmp_path: Path) -> None:
    """Blank pages are omitted without renumbering later text pages."""
    path = tmp_path / "with-empty-page.pdf"
    create_pdf(path, ["Visible text", None, "Final text"])

    result = PDFParser().parse(path)

    assert result.pages == [
        DocumentPage(page_number=1, text="Visible text"),
        DocumentPage(page_number=3, text="Final text"),
    ]


def test_pdf_parser_does_not_extract_from_image_only_page(tmp_path: Path) -> None:
    """Image-only pages remain empty because the parser performs no OCR."""
    path = tmp_path / "image-only.pdf"
    with fitz.open() as document:
        page = document.new_page()
        pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 20, 20), False)
        pixmap.clear_with(255)
        page.insert_image(page.rect, pixmap=pixmap)
        document.save(path)

    result = PDFParser().parse(path)

    assert result == DocumentContent(filename="image-only.pdf", pages=[])


def test_default_registry_contains_pdf_parser() -> None:
    """The application registry resolves PDF files to the concrete parser."""
    get_parser_registry.cache_clear()

    parser = get_parser_registry().get(Path("document.PDF"))

    assert isinstance(parser, PDFParser)
