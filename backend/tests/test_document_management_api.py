"""Tests for administrator document listing and deletion."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token
from app.core.config import Settings, get_settings
from app.main import app
from app.models.document import DocumentStatus
from app.rag.dependencies import get_qdrant_repository
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository


class FakeQdrantRepository:
    """Record deleted document IDs without contacting Qdrant."""

    def __init__(self) -> None:
        """Initialize an empty deletion record."""
        self.deleted_document_ids: list[int] = []

    def delete_document(self, document_id: int) -> None:
        """Record one deleted document ID."""
        self.deleted_document_ids.append(document_id)


class UnavailableQdrantRepository:
    """Simulate an unavailable vector service during deletion."""

    def delete_document(self, document_id: int) -> None:
        """Fail every vector cleanup request like a network outage."""
        del document_id
        raise ConnectionError("Qdrant is unavailable")


def authenticate_admin(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
) -> int:
    """Create and authenticate an administrator for an API test."""
    with session_factory() as session:
        admin = UserRepository(session).create(
            username="document-manager",
            password_hash="hashed-password",
            is_admin=True,
        )
        admin_id = admin.id
    settings = get_settings()
    client.cookies.set(settings.auth_cookie_name, create_access_token(admin_id))
    return admin_id


@pytest.fixture
def management_upload_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Redirect managed document files to an isolated directory."""
    directory = tmp_path / "managed-uploads"
    settings: Settings = get_settings()
    monkeypatch.setattr(settings, "document_upload_dir", directory)
    directory.mkdir()
    return directory


@pytest.mark.asyncio
async def test_admin_lists_and_searches_documents(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    management_upload_dir: Path,
) -> None:
    """An administrator can list documents and search by filename or digest."""
    del management_upload_dir
    admin_id = authenticate_admin(client, session_factory)
    with session_factory() as session:
        repository = DocumentRepository(session)
        repository.create(
            filename="stored-guide.txt",
            original_filename="Network Guide.txt",
            sha256="a" * 64,
            file_size=10,
            uploader_id=admin_id,
        )
        repository.create(
            filename="stored-policy.pdf",
            original_filename="Policy.pdf",
            sha256="b" * 64,
            file_size=20,
            uploader_id=admin_id,
        )

    response = await client.get(
        "/api/admin/documents",
        params={"search": "network"},
    )
    digest_response = await client.get(
        "/api/admin/documents",
        params={"search": "bbbbbbbb"},
    )

    assert response.status_code == 200
    assert [item["original_filename"] for item in response.json()["data"]] == [
        "Network Guide.txt"
    ]
    assert digest_response.json()["data"][0]["original_filename"] == "Policy.pdf"


@pytest.mark.asyncio
async def test_admin_deletes_document_and_source_file(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    management_upload_dir: Path,
) -> None:
    """Deleting a document removes metadata, indexes, and its source file."""
    admin_id = authenticate_admin(client, session_factory)
    with session_factory() as session:
        document = DocumentRepository(session).create(
            filename="stored.txt",
            original_filename="Delete Me.txt",
            sha256="c" * 64,
            file_size=7,
            uploader_id=admin_id,
        )
        document_id = document.id
    source_path = management_upload_dir / "stored.txt"
    source_path.write_text("content", encoding="utf-8")
    fake_qdrant = FakeQdrantRepository()
    app.dependency_overrides[get_qdrant_repository] = lambda: fake_qdrant

    response = await client.delete(f"/api/admin/documents/{document_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not source_path.exists()
    assert fake_qdrant.deleted_document_ids == [document_id]
    with session_factory() as session:
        assert DocumentRepository(session).get_by_id(document_id) is None


@pytest.mark.asyncio
async def test_admin_deletion_keeps_the_row_when_qdrant_is_unavailable(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    management_upload_dir: Path,
) -> None:
    """Vector cleanup failure leaves a visible pending_delete document.

    Deleting the row while Qdrant still holds its points is what produced
    orphaned vectors, and every later citation for the same subject failed.
    """
    admin_id = authenticate_admin(client, session_factory)
    with session_factory() as session:
        document = DocumentRepository(session).create(
            filename="offline-vector.txt",
            original_filename="Offline Vector.txt",
            sha256="d" * 64,
            file_size=7,
            uploader_id=admin_id,
        )
        document_id = document.id
    source_path = management_upload_dir / document.filename
    source_path.write_text("content", encoding="utf-8")
    app.dependency_overrides[get_qdrant_repository] = UnavailableQdrantRepository

    response = await client.delete(f"/api/admin/documents/{document_id}")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "message": "Document deletion service is unavailable",
    }
    assert source_path.exists()
    with session_factory() as session:
        stored = DocumentRepository(session).get_by_id(document_id)
        assert stored is not None
        assert stored.status is DocumentStatus.PENDING_DELETE


@pytest.mark.asyncio
async def test_admin_deletion_retry_finishes_an_interrupted_delete(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    management_upload_dir: Path,
) -> None:
    """Retrying after the vector service recovers removes the pending document."""
    admin_id = authenticate_admin(client, session_factory)
    with session_factory() as session:
        document = DocumentRepository(session).create(
            filename="retry-delete.txt",
            original_filename="Retry Delete.txt",
            sha256="e" * 64,
            file_size=7,
            uploader_id=admin_id,
        )
        document_id = document.id
    source_path = management_upload_dir / document.filename
    source_path.write_text("content", encoding="utf-8")
    app.dependency_overrides[get_qdrant_repository] = UnavailableQdrantRepository
    failed_response = await client.delete(f"/api/admin/documents/{document_id}")
    assert failed_response.status_code == 503

    fake_qdrant = FakeQdrantRepository()
    app.dependency_overrides[get_qdrant_repository] = lambda: fake_qdrant
    retried_response = await client.delete(f"/api/admin/documents/{document_id}")

    assert retried_response.status_code == 200
    assert fake_qdrant.deleted_document_ids == [document_id]
    assert not source_path.exists()
    with session_factory() as session:
        assert DocumentRepository(session).get_by_id(document_id) is None
