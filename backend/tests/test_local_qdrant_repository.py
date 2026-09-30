"""Tests for the persistent local Qdrant repository."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.models.chunk import Chunk
from app.repositories.qdrant import QdrantRepository


class FakeEmbeddingModel:
    """Expose a configurable sentence embedding dimension."""

    def __init__(self, dimension: int | None = 3) -> None:
        """Initialize the fake model dimension."""
        self.dimension = dimension
        self.call_count = 0

    def get_sentence_embedding_dimension(self) -> int | None:
        """Return and record the configured vector dimension."""
        self.call_count += 1
        return self.dimension


def create_chunk(
    *,
    chunk_id: str,
    document_id: int | None,
    chunk_index: int,
    text: str,
    page: int | None = 1,
    section: str | None = "Routing",
) -> Chunk:
    """Create one domain chunk for local persistence tests."""
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        page=page,
        section=section,
        chunk_index=chunk_index,
        text=text,
        token_count=len(text.split()),
    )


@pytest.fixture
def local_repository(tmp_path: Path) -> Iterator[QdrantRepository]:
    """Provide a closed local repository backed by a temporary directory."""
    repository = QdrantRepository(
        FakeEmbeddingModel(),
        path=tmp_path / "qdrant",
    )
    try:
        yield repository
    finally:
        repository.close()


def test_create_collection_is_idempotent_and_uses_model_dimension(
    tmp_path: Path,
) -> None:
    """Collection creation reads dimension once and persists in Local mode."""
    model = FakeEmbeddingModel(dimension=3)
    data_path = tmp_path / "qdrant"
    repository = QdrantRepository(model, path=data_path)
    try:
        repository.create_collection()
        repository.create_collection()

        assert model.call_count == 1
        assert repository.vector_dimension == 3
        assert data_path.exists()
    finally:
        repository.close()


def test_upsert_chunks_and_search_local_collection(
    local_repository: QdrantRepository,
) -> None:
    """Chunk vectors and payload metadata are searchable locally."""
    chunks = [
        create_chunk(
            chunk_id="doc-1-chunk-0",
            document_id=1,
            chunk_index=0,
            text="OSPF routing",
            page=3,
            section="Routing",
        ),
        create_chunk(
            chunk_id="doc-2-chunk-0",
            document_id=2,
            chunk_index=0,
            text="VLAN switching",
            page=5,
            section="Switching",
        ),
    ]

    local_repository.upsert_chunks(
        chunks,
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    results = local_repository.search([1.0, 0.0, 0.0], limit=2)

    assert len(results) == 2
    assert results[0].document_id == 1
    assert results[0].content == "OSPF routing"
    assert results[0].page == 3
    assert results[0].section == "Routing"
    assert results[0].chunk_index == 0


def test_delete_document_removes_only_its_chunks(
    local_repository: QdrantRepository,
) -> None:
    """Deleting one document preserves chunks from other documents."""
    chunks = [
        create_chunk(
            chunk_id="doc-1-chunk-0",
            document_id=1,
            chunk_index=0,
            text="OSPF routing",
        ),
        create_chunk(
            chunk_id="doc-2-chunk-0",
            document_id=2,
            chunk_index=0,
            text="VLAN switching",
        ),
    ]
    local_repository.upsert_chunks(
        chunks,
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )

    local_repository.delete_document(1)
    results = local_repository.search([1.0, 0.0, 0.0], limit=10)

    assert [result.document_id for result in results] == [2]


def test_search_returns_empty_when_collection_does_not_exist(
    local_repository: QdrantRepository,
) -> None:
    """Searching before collection creation returns no candidates."""
    assert local_repository.search([1.0, 0.0, 0.0]) == []


def test_repository_validates_vector_dimension(
    local_repository: QdrantRepository,
) -> None:
    """Vectors must match the dimension read from the embedding model."""
    chunk = create_chunk(
        chunk_id="doc-1-chunk-0",
        document_id=1,
        chunk_index=0,
        text="OSPF",
    )

    with pytest.raises(ValueError, match="Expected vector dimension 3"):
        local_repository.upsert_chunks([chunk], [[1.0, 0.0]])
    with pytest.raises(ValueError, match="Expected vector dimension 3"):
        local_repository.search([1.0, 0.0])


def test_repository_requires_document_id(
    local_repository: QdrantRepository,
) -> None:
    """Unpersisted chunks cannot be inserted into document storage."""
    chunk = create_chunk(
        chunk_id="unpersisted",
        document_id=None,
        chunk_index=0,
        text="OSPF",
    )

    with pytest.raises(ValueError, match="document_id is required"):
        local_repository.upsert_chunks([chunk], [[1.0, 0.0, 0.0]])


@pytest.mark.parametrize("dimension", [None, 0, -1])
def test_repository_rejects_invalid_model_dimension(
    tmp_path: Path,
    dimension: int | None,
) -> None:
    """The embedding model must expose a positive vector dimension."""
    with pytest.raises(ValueError, match="positive dimension"):
        QdrantRepository(
            FakeEmbeddingModel(dimension),
            path=tmp_path / "qdrant",
        )
