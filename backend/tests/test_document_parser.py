"""Tests for the abstract document parsing framework."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token
from app.core.config import Settings, get_settings
from app.main import app
from app.models.document import Document, DocumentStatus
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.services.document_parser import (
    DocumentContent,
    DocumentPage,
    DocumentParsingService,
    Parser,
    ParserRegistry,
    UnsupportedParserError,
)
from app.services.document_parser.dependencies import get_parser_registry


class FakeParser(Parser):
    """Parse a test file into one page without representing a real format."""

    def parse(self, file_path: Path) -> DocumentContent:
        """Return deterministic page-preserving content for a test file."""
        return DocumentContent(
            filename=file_path.name,
            pages=[
                DocumentPage(
                    page_number=1,
                    text=file_path.read_text(encoding="utf-8"),
                )
            ],
        )


def create_stored_document(
    session: Session,
    upload_dir: Path,
    *,
    filename: str = "stored.test",
    content: str = "parsed content",
) -> Document:
    """Create a stored file and database record for framework tests."""
    user = UserRepository(session).create(
        username="parser-admin",
        password_hash="hashed-password",
        is_admin=True,
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / filename).write_text(content, encoding="utf-8")
    return DocumentRepository(session).create(
        filename=filename,
        original_filename=filename,
        sha256="d" * 64,
        file_size=len(content.encode()),
        uploader_id=user.id,
    )


def create_registry() -> ParserRegistry:
    """Return a registry containing only the test parser."""
    registry = ParserRegistry()
    registry.register("test", FakeParser())
    return registry


def test_parser_is_abstract() -> None:
    """The parser contract cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Parser()


def test_parser_returns_filename_and_pages(tmp_path: Path) -> None:
    """A parser implementation returns the required paged data structure."""
    path = tmp_path / "document.test"
    path.write_text("page text", encoding="utf-8")

    result = FakeParser().parse(path)

    assert result == DocumentContent(
        filename="document.test",
        pages=[DocumentPage(page_number=1, text="page text")],
    )


def test_parser_registry_selects_injected_parser() -> None:
    """The registry selects parsers by normalized case-insensitive extension."""
    parser = FakeParser()
    registry = ParserRegistry()
    registry.register(".TEST", parser)

    assert registry.get(Path("document.test")) is parser
    with pytest.raises(UnsupportedParserError):
        registry.get(Path("document.pdf"))


def test_parsing_service_updates_completed_status(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    """An injected parser completes parsing and status transition."""
    with session_factory() as session:
        document = create_stored_document(session, tmp_path)

        result = DocumentParsingService(
            DocumentRepository(session),
            tmp_path,
            create_registry(),
        ).parse(document)

        assert result.pages[0].text == "parsed content"
        assert document.status is DocumentStatus.COMPLETED


@pytest.mark.asyncio
async def test_parse_endpoint_uses_injected_parser_framework(
    client: httpx.AsyncClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parsing endpoint serializes page-preserving parser output."""
    settings: Settings = get_settings()
    monkeypatch.setattr(settings, "document_upload_dir", tmp_path)

    def override_parser_registry() -> ParserRegistry:
        """Return the parser registry used by the endpoint test."""
        return create_registry()

    app.dependency_overrides[get_parser_registry] = override_parser_registry
    with session_factory() as session:
        document = create_stored_document(session, tmp_path)
        document_id = document.id
        uploader_id = document.uploader_id
    client.cookies.set(
        settings.auth_cookie_name,
        create_access_token(uploader_id),
    )

    response = await client.post(f"/api/admin/documents/{document_id}/parse")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "data": {
            "filename": "stored.test",
            "pages": [{"page_number": 1, "text": "parsed content"}],
        },
    }
