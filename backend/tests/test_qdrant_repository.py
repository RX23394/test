"""Tests for Qdrant chunk persistence."""

from qdrant_client import QdrantClient

from app.models.document import Document
from app.repositories.qdrant import QdrantChunkRepository
from app.schemas.chunk import Chunk
from app.services.embedding import EMBEDDING_DIMENSION


def create_document() -> Document:
    """Return document metadata suitable for vector repository tests."""
    return Document(
        id=7,
        filename="stored.md",
        original_filename="guide.md",
        sha256="e" * 64,
        file_size=100,
        uploader_id=3,
    )


def test_qdrant_repository_replaces_document_chunks() -> None:
    """Chunk points contain retrieval payloads and replace older points."""
    client = QdrantClient(location=":memory:")
    repository = QdrantChunkRepository(
        url="http://unused",
        collection_name="test_chunks",
        client=client,
    )
    document = create_document()
    chunks = [
        Chunk(
            content="first content",
            page=1,
            section="Intro",
            chunk_index=0,
        ),
        Chunk(
            content="second content",
            page=2,
            section="Details",
            chunk_index=1,
        ),
    ]
    vectors = [[0.1] * EMBEDDING_DIMENSION, [0.2] * EMBEDDING_DIMENSION]

    repository.replace_document_chunks(document, chunks, vectors)
    points, _ = client.scroll(
        collection_name="test_chunks",
        limit=10,
        with_payload=True,
        with_vectors=True,
    )

    assert len(points) == 2
    payloads = sorted(
        (point.payload or {} for point in points),
        key=lambda payload: int(payload["chunk_index"]),
    )
    assert payloads[0] == {
        "document_id": 7,
        "filename": "stored.md",
        "original_filename": "guide.md",
        "sha256": "e" * 64,
        "content": "first content",
        "page": 1,
        "section": "Intro",
        "chunk_index": 0,
    }
    candidates = repository.search([0.1] * EMBEDDING_DIMENSION, limit=20)
    assert len(candidates) == 2
    assert {candidate.chunk_index for candidate in candidates} == {0, 1}

    repository.replace_document_chunks(document, chunks[:1], vectors[:1])
    replaced_points, _ = client.scroll(
        collection_name="test_chunks",
        limit=10,
    )
    assert len(replaced_points) == 1
