"""UTF-8 Markdown document parser."""

from pathlib import Path

from app.services.document_parser.base import Parser
from app.services.document_parser.models import DocumentContent, DocumentPage


class MarkdownParser(Parser):
    """Read Markdown source while preserving its heading markers."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Return raw UTF-8 Markdown as one hierarchy-preserving page."""
        text = file_path.read_text(encoding="utf-8").strip()
        pages = [DocumentPage(page_number=1, text=text)] if text else []
        return DocumentContent(filename=file_path.name, pages=pages)
