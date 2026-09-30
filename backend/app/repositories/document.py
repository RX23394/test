"""Document repository."""

from collections.abc import Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    """Persist and query documents through a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self._session = session

    def get_by_id(self, document_id: int) -> Document | None:
        """Return a document by primary key."""
        return self._session.get(Document, document_id)

    def get_by_ids(self, document_ids: Sequence[int]) -> dict[int, Document]:
        """Return documents keyed by ID for a search result batch."""
        if not document_ids:
            return {}
        statement = select(Document).where(Document.id.in_(set(document_ids)))
        documents = self._session.scalars(statement).all()
        return {document.id: document for document in documents}

    def get_by_sha256(self, sha256: str) -> Document | None:
        """Return the first document matching a SHA-256 digest."""
        statement = select(Document).where(Document.sha256 == sha256)
        return self._session.scalars(statement).first()

    def list_by_uploader(self, uploader_id: int) -> Sequence[Document]:
        """Return documents uploaded by a user, newest first."""
        statement = (
            select(Document)
            .where(Document.uploader_id == uploader_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
        )
        return self._session.scalars(statement).all()

    def list_all(self, search: str | None = None) -> Sequence[Document]:
        """Return all documents, optionally filtered by filename or digest."""
        statement = select(Document)
        normalized_search = search.strip() if search else ""
        if normalized_search:
            pattern = f"%{normalized_search}%"
            statement = statement.where(
                or_(
                    Document.original_filename.ilike(pattern),
                    Document.sha256.ilike(pattern),
                )
            )
        statement = statement.order_by(
            Document.created_at.desc(),
            Document.id.desc(),
        )
        return self._session.scalars(statement).all()

    def create(
        self,
        *,
        filename: str,
        original_filename: str,
        sha256: str,
        file_size: int,
        uploader_id: int,
        status: DocumentStatus = DocumentStatus.PENDING,
    ) -> Document:
        """Create and persist a document."""
        document = Document(
            filename=filename,
            original_filename=original_filename,
            sha256=sha256,
            file_size=file_size,
            uploader_id=uploader_id,
            status=status,
        )
        self._session.add(document)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        self._session.refresh(document)
        return document

    def update_status(
        self,
        document: Document,
        status: DocumentStatus,
        *,
        commit: bool = True,
    ) -> Document:
        """Update a status immediately or within the caller's transaction."""
        document.status = status
        try:
            if commit:
                self._session.commit()
                self._session.refresh(document)
            else:
                self._session.flush()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return document

    def claim_for_indexing(self, document_id: int, job_id: str) -> Document | None:
        """Atomically claim a retryable document for one indexing job."""
        statement = (
            update(Document)
            .where(
                Document.id == document_id,
                Document.status.in_((DocumentStatus.PENDING, DocumentStatus.FAILED)),
            )
            .values(
                status=DocumentStatus.PROCESSING,
                indexing_job_id=job_id,
            )
        )
        try:
            result = self._session.execute(statement)
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        if result.rowcount != 1:
            return None
        self._session.expire_all()
        return self._session.get(Document, document_id)

    def is_indexing_owner(self, document_id: int, job_id: str) -> bool:
        """Return whether a job still owns a document indexing task."""
        statement = select(Document.id).where(
            Document.id == document_id,
            Document.status == DocumentStatus.PROCESSING,
            Document.indexing_job_id == job_id,
        )
        return self._session.scalar(statement) is not None

    def complete_indexing(self, document_id: int, job_id: str) -> bool:
        """Mark an indexing job complete only when it still owns the task."""
        return self._finish_indexing_job(
            document_id,
            job_id,
            DocumentStatus.INDEXED,
        )

    def fail_indexing(self, document_id: int, job_id: str) -> bool:
        """Mark an indexing job failed only when it still owns the task."""
        return self._finish_indexing_job(
            document_id,
            job_id,
            DocumentStatus.FAILED,
        )

    def _finish_indexing_job(
        self,
        document_id: int,
        job_id: str,
        status: DocumentStatus,
    ) -> bool:
        """Atomically finalize the owned processing task."""
        statement = (
            update(Document)
            .where(
                Document.id == document_id,
                Document.status == DocumentStatus.PROCESSING,
                Document.indexing_job_id == job_id,
            )
            .values(status=status, indexing_job_id=None)
        )
        try:
            result = self._session.execute(statement)
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return result.rowcount == 1

    def delete(self, document: Document) -> None:
        """Delete a document and commit the database transaction."""
        self._session.delete(document)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
