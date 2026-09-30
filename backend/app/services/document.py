"""Document upload service."""

import hashlib
import logging
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.models.document import Document
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)

ALLOWED_DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx", ".md", ".txt"})
UPLOAD_CHUNK_SIZE = 1024 * 1024


class UnsupportedDocumentTypeError(ValueError):
    """Raised when an uploaded filename has an unsupported extension."""


class DocumentTooLargeError(ValueError):
    """Raised when an uploaded document exceeds the configured size limit."""


class DuplicateDocumentError(ValueError):
    """Raised when a document with the same SHA-256 digest already exists."""


class DocumentUploadService:
    """Store uploaded files and create their document records."""

    def __init__(
        self,
        repository: DocumentRepository,
        upload_dir: Path,
        max_upload_bytes: int,
    ) -> None:
        """Initialize the service with persistence and storage dependencies."""
        self._repository = repository
        self._upload_dir = upload_dir
        self._max_upload_bytes = max_upload_bytes

    def upload(
        self,
        *,
        source: BinaryIO,
        original_filename: str,
        uploader_id: int,
    ) -> Document:
        """Store a supported file and persist its calculated metadata."""
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise UnsupportedDocumentTypeError

        self._upload_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4()}{extension}"
        destination = self._upload_dir / stored_filename
        temporary_path = self._upload_dir / f".{stored_filename}.uploading"

        try:
            sha256, file_size = self._write_and_hash(source, temporary_path)
            if self._repository.get_by_sha256(sha256) is not None:
                raise DuplicateDocumentError

            temporary_path.replace(destination)
            try:
                document = self._repository.create(
                    filename=stored_filename,
                    original_filename=original_filename,
                    sha256=sha256,
                    file_size=file_size,
                    uploader_id=uploader_id,
                )
            except IntegrityError as exc:
                raise DuplicateDocumentError from exc
        except Exception:
            self._remove_if_exists(temporary_path)
            self._remove_if_exists(destination)
            raise

        logger.info(
            "Document uploaded",
            extra={"document_id": document.id, "uploader_id": uploader_id},
        )
        return document

    def _write_and_hash(
        self,
        source: BinaryIO,
        temporary_path: Path,
    ) -> tuple[str, int]:
        """Write an upload to disk while calculating its digest and size."""
        digest = hashlib.sha256()
        file_size = 0

        with temporary_path.open("xb") as destination:
            while chunk := source.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > self._max_upload_bytes:
                    raise DocumentTooLargeError
                digest.update(chunk)
                destination.write(chunk)

        return digest.hexdigest(), file_size

    @staticmethod
    def _remove_if_exists(path: Path) -> None:
        """Remove a partially stored upload if it exists."""
        path.unlink(missing_ok=True)
