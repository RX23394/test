"""Tests for the standalone SQLite FTS5 chunk index."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.fts import ChunkIndexEntry, ChunkIndexRepository


def test_chunk_index_has_only_required_business_columns(
    session_factory: sessionmaker[Session],
) -> None:
    """The FTS5 table exposes chunk ID, document ID, and content fields."""
    with session_factory() as session:
        rows = session.execute(text("PRAGMA table_info(chunk_index)")).mappings()
        columns = [str(row["name"]) for row in rows]

    assert columns == ["chunk_id", "document_id", "content"]


def test_insert_and_full_text_search(
    session_factory: sessionmaker[Session],
) -> None:
    """Inserted content is found through native FTS5 full-text matching."""
    with session_factory() as session:
        repository = ChunkIndexRepository(session)
        repository.insert("chunk-1", 10, "OSPF is a link-state routing protocol")
        repository.insert("chunk-2", 20, "VLAN separates broadcast domains")

        results = repository.search("link-state routing")

    assert results == [
        ChunkIndexEntry(
            chunk_id="chunk-1",
            document_id=10,
            content="OSPF is a link-state routing protocol",
        )
    ]


def test_insert_replaces_existing_chunk_id(
    session_factory: sessionmaker[Session],
) -> None:
    """Reinserting a chunk ID replaces its previous indexed content."""
    with session_factory() as session:
        repository = ChunkIndexRepository(session)
        repository.insert("chunk-1", 10, "old routing content")
        repository.insert("chunk-1", 10, "new switching content")

        old_results = repository.search("old")
        new_results = repository.search("switching")

    assert old_results == []
    assert len(new_results) == 1
    assert new_results[0].content == "new switching content"


def test_delete_removes_only_selected_chunk(
    session_factory: sessionmaker[Session],
) -> None:
    """Deleting by chunk ID leaves other full-text rows intact."""
    with session_factory() as session:
        repository = ChunkIndexRepository(session)
        repository.insert("chunk-1", 10, "OSPF routing")
        repository.insert("chunk-2", 10, "BGP routing")

        repository.delete("chunk-1")
        results = repository.search("routing")

    assert [result.chunk_id for result in results] == ["chunk-2"]


def test_metadata_fields_are_not_full_text_indexed(
    session_factory: sessionmaker[Session],
) -> None:
    """Chunk and document identifiers do not participate in MATCH queries."""
    with session_factory() as session:
        repository = ChunkIndexRepository(session)
        repository.insert("uniquechunkidentifier", 987654, "network content")

        chunk_id_results = repository.search("uniquechunkidentifier")
        document_id_results = repository.search("987654")

    assert chunk_id_results == []
    assert document_id_results == []


def test_search_respects_limit_and_handles_blank_query(
    session_factory: sessionmaker[Session],
) -> None:
    """Search limits results and returns nothing for non-searchable input."""
    with session_factory() as session:
        repository = ChunkIndexRepository(session)
        repository.insert("chunk-1", 1, "routing one")
        repository.insert("chunk-2", 2, "routing two")

        limited = repository.search("routing", limit=1)
        blank = repository.search("---", limit=10)

    assert len(limited) == 1
    assert blank == []


def test_search_rejects_non_positive_limit(
    session_factory: sessionmaker[Session],
) -> None:
    """A full-text search limit must be positive."""
    with session_factory() as session:
        repository = ChunkIndexRepository(session)

        with pytest.raises(ValueError, match="limit must be positive"):
            repository.search("routing", limit=0)
