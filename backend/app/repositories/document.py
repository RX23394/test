"""Document repository."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, Update, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus


def _lease_deadline(lease_seconds: int) -> datetime:
    """Return the naive UTC instant before which a lease counts as expired.

    SQLite stores ``CURRENT_TIMESTAMP`` without a timezone, so the comparison
    value is built the same way to keep the comparison a plain string ordering.
    """
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=lease_seconds)


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

    def list_all(
        self,
        search: str | None = None,
        *,
        limit: int,
        offset: int = 0,
    ) -> Sequence[Document]:
        """Return one page of documents, optionally filtered by filename or digest."""
        statement = self._filtered_statement(search).order_by(
            Document.created_at.desc(),
            Document.id.desc(),
        )
        return self._session.scalars(statement.limit(limit).offset(offset)).all()

    def count_all(self, search: str | None = None) -> int:
        """Return the total number of matching documents, ignoring pagination."""
        statement = select(func.count()).select_from(
            self._filtered_statement(search).subquery()
        )
        return int(self._session.scalar(statement) or 0)

    def _filtered_statement(self, search: str | None) -> Select[tuple[Document]]:
        """Build the shared document filter used by listing and counting."""
        statement = select(Document)
        normalized_search = search.strip() if search else ""
        if not normalized_search:
            return statement
        pattern = f"%{normalized_search}%"
        return statement.where(
            or_(
                Document.original_filename.ilike(pattern),
                Document.sha256.ilike(pattern),
            )
        )

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
        """Create a document inside the caller's transaction."""
        document = Document(
            filename=filename,
            original_filename=original_filename,
            sha256=sha256,
            file_size=file_size,
            uploader_id=uploader_id,
            status=status,
        )
        self._session.add(document)
        self._session.flush()
        return document

    def update_status(self, document: Document, status: DocumentStatus) -> Document:
        """Update a document status inside the caller's transaction."""
        document.status = status
        self._session.flush()
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
                indexing_started_at=func.now(),
            )
        )
        result = self._session.execute(statement)
        if result.rowcount != 1:
            return None
        self._session.expire_all()
        return self._session.get(Document, document_id)

    def release_expired_lease(self, document_id: int, lease_seconds: int) -> bool:
        """Reset one expired processing lease so the document can be retried."""
        released = self._expired_lease_update(lease_seconds).where(
            Document.id == document_id
        )
        return self._execute_lease_release(released) > 0

    def release_all_expired_leases(self, lease_seconds: int) -> int:
        """Reset every expired processing lease and return how many were reset."""
        return self._execute_lease_release(self._expired_lease_update(lease_seconds))

    def _expired_lease_update(self, lease_seconds: int) -> Update:
        """Build the update that fails documents whose indexing lease expired.

        A ``PROCESSING`` row without a lease timestamp predates this feature (or
        was left by an interrupted claim), so it is treated as expired too.
        """
        deadline = _lease_deadline(lease_seconds)
        return (
            update(Document)
            .where(
                Document.status == DocumentStatus.PROCESSING,
                or_(
                    Document.indexing_started_at.is_(None),
                    Document.indexing_started_at < deadline,
                ),
            )
            .values(
                status=DocumentStatus.FAILED,
                indexing_job_id=None,
                indexing_started_at=None,
            )
        )

    def _execute_lease_release(self, statement: Update) -> int:
        """Execute a lease release update and return the affected row count."""
        result = self._session.execute(statement)
        self._session.expire_all()
        return int(result.rowcount or 0)

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
            .values(
                status=status,
                indexing_job_id=None,
                indexing_started_at=None,
            )
        )
        result = self._session.execute(statement)
        return result.rowcount == 1

    def delete(self, document: Document) -> None:
        """Delete a document inside the caller's transaction."""
        self._session.delete(document)
        self._session.flush()
