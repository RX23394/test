"""Microsoft Word document parser."""

from pathlib import Path

from docx import Document

from app.services.document_parser.base import Parser
from app.services.document_parser.models import DocumentContent, DocumentPage


class DocxParser(Parser):
    """Extract paragraph text from DOCX files as one logical page."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Read non-empty DOCX paragraphs in their document order."""
        document = Document(file_path)
        text = "\n".join(
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        )
        pages = [DocumentPage(page_number=1, text=text)] if text else []
        return DocumentContent(filename=file_path.name, pages=pages)
