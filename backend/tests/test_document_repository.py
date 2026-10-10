"""Tests for document persistence and schemas."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.models.document import DocumentStatus
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.schemas.document import DocumentCreate, DocumentResponse


def test_create_and_query_document(
    session_factory: sessionmaker[Session],
) -> None:
    """Persist a document and query it by its supported lookup fields."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="document-owner",
            password_hash="hashed-password",
        )
        repository = DocumentRepository(session)
        document = repository.create(
            filename="stored.pdf",
            original_filename="network guide.pdf",
            sha256="a" * 64,
            file_size=4096,
            uploader_id=user.id,
        )

        assert document.id is not None
        assert document.status is DocumentStatus.PENDING
        assert document.uploader.id == user.id
        assert repository.get_by_id(document.id) == document
        assert repository.get_by_sha256("a" * 64) == document
        assert list(repository.list_by_uploader(user.id)) == [document]


def test_update_document_status(
    session_factory: sessionmaker[Session],
) -> None:
    """Persist document status changes through the repository."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="status-owner",
            password_hash="hashed-password",
        )
        repository = DocumentRepository(session)
        document = repository.create(
            filename="stored.txt",
            original_filename="notes.txt",
            sha256="b" * 64,
            file_size=128,
            uploader_id=user.id,
        )

        updated = repository.update_status(document, DocumentStatus.COMPLETED)

        assert updated.status is DocumentStatus.COMPLETED


def test_indexing_lease_can_be_released_after_it_expires(
    session_factory: sessionmaker[Session],
) -> None:
    """A stale processing claim is reset so the document can be indexed again."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="lease-owner",
            password_hash="hashed-password",
        )
        repository = DocumentRepository(session)
        document = repository.create(
            filename="lease.md",
            original_filename="lease.md",
            sha256="d" * 64,
            file_size=64,
            uploader_id=user.id,
        )

        claimed = repository.claim_for_indexing(document.id, "job-a")
        assert claimed is not None
        assert claimed.status is DocumentStatus.PROCESSING
        assert claimed.indexing_started_at is not None
        assert repository.claim_for_indexing(document.id, "job-b") is None

        # Simulate a worker that died 20 minutes ago.
        claimed.indexing_started_at = datetime.now(UTC).replace(
            tzinfo=None
        ) - timedelta(minutes=20)
        session.commit()

        assert repository.release_expired_lease(document.id, 900) is True
        released = repository.get_by_id(document.id)
        assert released is not None
        assert released.status is DocumentStatus.FAILED
        assert released.indexing_job_id is None
        assert released.indexing_started_at is None
        assert repository.claim_for_indexing(document.id, "job-b") is not None


def test_indexing_lease_is_kept_while_still_running(
    session_factory: sessionmaker[Session],
) -> None:
    """A live lease is neither released nor counted by the sweep."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="live-lease-owner",
            password_hash="hashed-password",
        )
        repository = DocumentRepository(session)
        live = repository.create(
            filename="live.md",
            original_filename="live.md",
            sha256="e" * 64,
            file_size=64,
            uploader_id=user.id,
        )
        stale = repository.create(
            filename="stale.md",
            original_filename="stale.md",
            sha256="f" * 64,
            file_size=64,
            uploader_id=user.id,
        )
        assert repository.claim_for_indexing(live.id, "job-live") is not None
        claimed_stale = repository.claim_for_indexing(stale.id, "job-stale")
        assert claimed_stale is not None
        claimed_stale.indexing_started_at = datetime.now(UTC).replace(
            tzinfo=None
        ) - timedelta(hours=2)
        session.commit()

        released = repository.release_all_expired_leases(900)

        assert released == 1
        assert repository.is_indexing_owner(live.id, "job-live") is True
        assert repository.is_indexing_owner(stale.id, "job-stale") is False


def test_finished_indexing_job_clears_its_lease(
    session_factory: sessionmaker[Session],
) -> None:
    """Completing or failing a job drops the lease fields."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="lease-cleanup-owner",
            password_hash="hashed-password",
        )
        repository = DocumentRepository(session)
        document = repository.create(
            filename="done.md",
            original_filename="done.md",
            sha256="1" * 64,
            file_size=64,
            uploader_id=user.id,
        )
        assert repository.claim_for_indexing(document.id, "job-done") is not None

        assert repository.complete_indexing(document.id, "job-done") is True

        finished = repository.get_by_id(document.id)
        assert finished is not None
        assert finished.status is DocumentStatus.INDEXED
        assert finished.indexing_job_id is None
        assert finished.indexing_started_at is None


def test_document_schema_serializes_model(
    session_factory: sessionmaker[Session],
) -> None:
    """Validate creation metadata and serialize a persisted document."""
    payload = DocumentCreate(
        filename="stored.md",
        original_filename="readme.md",
        sha256="c" * 64,
        file_size=512,
        uploader_id=1,
    )

    with session_factory() as session:
        user = UserRepository(session).create(
            username="schema-owner",
            password_hash="hashed-password",
        )
        document = DocumentRepository(session).create(
            **payload.model_dump(exclude={"uploader_id"}),
            uploader_id=user.id,
        )
        response = DocumentResponse.model_validate(document)

    assert response.filename == payload.filename
    assert response.status is DocumentStatus.PENDING
    assert response.created_at is not None
