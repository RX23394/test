"""UTF-8 plain-text document parser."""

from pathlib import Path

from app.services.document_parser.base import Parser
from app.services.document_parser.models import DocumentContent, DocumentPage


class TxtParser(Parser):
    """Read UTF-8 plain-text files as one logical page."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Return UTF-8 text without introducing processing stages."""
        text = file_path.read_text(encoding="utf-8").strip()
        pages = [DocumentPage(page_number=1, text=text)] if text else []
        return DocumentContent(filename=file_path.name, pages=pages)
