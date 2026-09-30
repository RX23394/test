"""Abstract document parser contract."""

from abc import ABC, abstractmethod
from pathlib import Path

from app.services.document_parser.models import DocumentContent


class Parser(ABC):
    """Abstract base class implemented by document format parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> DocumentContent:
        """Parse a file into page-preserving document content."""
        raise NotImplementedError
