"""Tests for the administrator document upload endpoint."""

import hashlib
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token
from app.core.config import Settings, get_settings
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository


def authenticate_user(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    *,
    is_admin: bool,
) -> int:
    """Create a user and place their authentication token in the client."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="upload-user",
            password_hash="hashed-password",
            is_admin=is_admin,
        )
        user_id = user.id

    settings = get_settings()
    client.cookies.set(
        settings.auth_cookie_name,
        create_access_token(user_id),
    )
    return user_id


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect uploaded files to an isolated temporary directory."""
    directory = tmp_path / "uploads"
    settings: Settings = get_settings()
    monkeypatch.setattr(settings, "document_upload_dir", directory)
    return directory


@pytest.mark.asyncio
@pytest.mark.parametrize("extension", ["pdf", "docx", "md", "txt"])
async def test_admin_uploads_document(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    upload_dir: Path,
    extension: str,
) -> None:
    """An administrator can store every supported document type."""
    uploader_id = authenticate_user(client, session_factory, is_admin=True)
    content = f"network {extension} document".encode()

    response = await client.post(
        "/api/admin/documents",
        files={"file": (f"guide.{extension}", content, "application/octet-stream")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["original_filename"] == f"guide.{extension}"
    assert payload["data"]["file_size"] == len(content)
    assert payload["data"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert payload["data"]["uploader_id"] == uploader_id
    stored_filename = payload["data"]["filename"]
    stored_path = Path(stored_filename)
    assert stored_path.suffix == f".{extension}"
    UUID(stored_path.stem)
    assert (upload_dir / stored_filename).read_bytes() == content

    with session_factory() as session:
        document = DocumentRepository(session).get_by_sha256(
            hashlib.sha256(content).hexdigest()
        )
        assert document is not None
        assert document.filename == stored_filename


@pytest.mark.asyncio
async def test_upload_requires_an_administrator(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    upload_dir: Path,
) -> None:
    """A non-administrator cannot use the document upload endpoint."""
    del upload_dir
    authenticate_user(client, session_factory, is_admin=False)

    response = await client.post(
        "/api/admin/documents",
        files={"file": ("guide.txt", b"content", "text/plain")},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "Administrator access required"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    upload_dir: Path,
) -> None:
    """An unsupported filename extension is rejected without storing a file."""
    authenticate_user(client, session_factory, is_admin=True)

    response = await client.post(
        "/api/admin/documents",
        files={"file": ("image.png", b"content", "image/png")},
    )

    assert response.status_code == 415
    assert not upload_dir.exists()


@pytest.mark.asyncio
async def test_upload_rejects_oversized_document(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A document over the configured limit is rejected and cleaned up."""
    authenticate_user(client, session_factory, is_admin=True)
    monkeypatch.setattr(get_settings(), "document_max_upload_bytes", 4)

    response = await client.post(
        "/api/admin/documents",
        files={"file": ("large.md", b"12345", "text/markdown")},
    )

    assert response.status_code == 413
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_rejects_duplicate_document(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    upload_dir: Path,
) -> None:
    """Uploading identical content twice returns conflict without another file."""
    authenticate_user(client, session_factory, is_admin=True)
    files = {"file": ("first.docx", b"same-content", "application/octet-stream")}
    first_response = await client.post("/api/admin/documents", files=files)

    duplicate_response = await client.post(
        "/api/admin/documents",
        files={"file": ("second.txt", b"same-content", "text/plain")},
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["message"] == "Document already exists"
    assert len(list(upload_dir.iterdir())) == 1
