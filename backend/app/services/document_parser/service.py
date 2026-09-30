"""Document parsing orchestration independent of concrete parsers."""

import logging
from pathlib import Path

from app.models.document import Document, DocumentStatus
from app.repositories.document import DocumentRepository
from app.services.document_parser.models import DocumentContent
from app.services.document_parser.registry import ParserRegistry

logger = logging.getLogger(__name__)


class DocumentParseError(ValueError):
    """Raised by parser implementations when extraction fails."""


class DocumentFileNotFoundError(FileNotFoundError):
    """Raised when a persisted document file is missing."""


class DocumentParsingService:
    """Coordinate parser selection and document status transitions."""

    def __init__(
        self,
        repository: DocumentRepository,
        upload_dir: Path,
        registry: ParserRegistry,
        *,
        manage_status: bool = True,
    ) -> None:
        """Initialize the service with persistence, storage, and parser registry."""
        self._repository = repository
        self._upload_dir = upload_dir
        self._registry = registry
        self._manage_status = manage_status

    def parse(self, document: Document) -> DocumentContent:
        """Parse a stored document through its registered parser."""
        if self._manage_status:
            self._repository.update_status(document, DocumentStatus.PROCESSING)

        try:
            path = self._resolve_document_path(document.filename)
            parser = self._registry.get(path)
            content = parser.parse(path)
        except Exception:
            if self._manage_status:
                self._repository.update_status(document, DocumentStatus.FAILED)
            logger.exception(
                "Document parsing failed",
                extra={"document_id": document.id},
            )
            raise

        if self._manage_status:
            self._repository.update_status(document, DocumentStatus.COMPLETED)
        logger.info(
            "Document parsed",
            extra={"document_id": document.id},
        )
        return content

    def _resolve_document_path(self, filename: str) -> Path:
        """Resolve a stored filename without allowing directory traversal."""
        upload_dir = self._upload_dir.resolve()
        path = (upload_dir / filename).resolve()
        if not path.is_relative_to(upload_dir) or not path.is_file():
            raise DocumentFileNotFoundError
        return path
