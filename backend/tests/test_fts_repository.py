"""Tests for SQLite FTS5 chunk persistence and retrieval."""

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.repositories.user import UserRepository
from app.schemas.chunk import Chunk


def test_fts_repository_replaces_and_searches_chunks(
    session_factory: sessionmaker[Session],
) -> None:
    """FTS5 returns matching chunks and removes replaced document rows."""
    with session_factory() as session:
        user = UserRepository(session).create(
            username="fts-owner",
            password_hash="hashed-password",
        )
        document = DocumentRepository(session).create(
            filename="stored.md",
            original_filename="guide.md",
            sha256="1" * 64,
            file_size=100,
            uploader_id=user.id,
        )
        repository = FtsChunkRepository(session)
        chunks = [
            Chunk(
                content="OSPF routing protocol",
                page=3,
                section="Routing",
                chunk_index=0,
            ),
            Chunk(
                content="Ethernet switching",
                page=4,
                section="Switching",
                chunk_index=1,
            ),
        ]

        repository.replace_document_chunks(document, chunks)
        results = repository.search("OSPF", limit=20)

        assert len(results) == 1
        assert results[0].document_id == document.id
        assert results[0].chunk_index == 0
        assert results[0].page == 3
        assert results[0].section == "Routing"

        repository.replace_document_chunks(document, chunks[1:])
        assert repository.search("OSPF", limit=20) == []
