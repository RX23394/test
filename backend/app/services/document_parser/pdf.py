"""Text-only PDF document parser."""

from pathlib import Path

import fitz

from app.services.document_parser.base import Parser
from app.services.document_parser.models import DocumentContent, DocumentPage


class PDFParser(Parser):
    """Extract page-preserving text from text-based PDF documents."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Read PDF text page by page while omitting pages without text."""
        pages: list[DocumentPage] = []

        with fitz.open(file_path) as document:
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if not text:
                    continue
                pages.append(DocumentPage(page_number=page_number, text=text))

        return DocumentContent(filename=file_path.name, pages=pages)
