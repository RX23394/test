"""Tests for document persistence and schemas."""

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
