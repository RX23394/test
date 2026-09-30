"""Qdrant repository for document chunk vectors."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.models.chunk import Chunk as DomainChunk
from app.models.document import Document
from app.schemas.chunk import Chunk
from app.schemas.search import RetrievalCandidate
from app.services.embedding import EMBEDDING_DIMENSION

QDRANT_UPSERT_BATCH_SIZE = 100
DEFAULT_LOCAL_QDRANT_PATH = Path(__file__).resolve().parents[3] / "data" / "qdrant"
DEFAULT_LOCAL_COLLECTION_NAME = "documents"


class EmbeddingModel(Protocol):
    """Embedding model dimension contract required by local Qdrant."""

    def get_sentence_embedding_dimension(self) -> int | None:
        """Return the model output vector dimension."""
        ...


class QdrantChunkRepository:
    """Replace and persist document chunk vectors in Qdrant."""

    def __init__(
        self,
        *,
        url: str,
        collection_name: str,
        api_key: str | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        """Initialize the repository with Qdrant connection settings."""
        self._collection_name = collection_name
        self._client = client or QdrantClient(url=url, api_key=api_key)

    def replace_document_chunks(
        self,
        document: Document,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Delete existing document points and write the supplied chunks."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")

        self._ensure_collection()
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document.id),
                        )
                    ]
                )
            ),
            wait=True,
        )

        points = [
            self._build_point(document, chunk, vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        for offset in range(0, len(points), QDRANT_UPSERT_BATCH_SIZE):
            self._client.upsert(
                collection_name=self._collection_name,
                points=points[offset : offset + QDRANT_UPSERT_BATCH_SIZE],
                wait=True,
            )

    def search(
        self,
        vector: Sequence[float],
        limit: int,
    ) -> list[RetrievalCandidate]:
        """Return cosine-ranked chunk candidates from Qdrant."""
        if not self._client.collection_exists(self._collection_name):
            return []
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=list(vector),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        candidates: list[RetrievalCandidate] = []
        for point in response.points:
            payload = point.payload or {}
            candidates.append(
                RetrievalCandidate(
                    document_id=int(payload["document_id"]),
                    chunk_index=int(payload["chunk_index"]),
                    content=str(payload["content"]),
                    page=(
                        int(payload["page"])
                        if payload.get("page") is not None
                        else None
                    ),
                    section=(
                        str(payload["section"])
                        if payload.get("section") is not None
                        else None
                    ),
                    score=float(point.score),
                )
            )
        return candidates

    def delete_document(self, document_id: int) -> None:
        """Delete all vector points belonging to one document."""
        if not self._client.collection_exists(self._collection_name):
            return
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def _ensure_collection(self) -> None:
        """Create the cosine-distance collection when it does not exist."""
        if self._client.collection_exists(self._collection_name):
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=models.Distance.COSINE,
            ),
        )

    def _build_point(
        self,
        document: Document,
        chunk: Chunk,
        vector: Sequence[float],
    ) -> models.PointStruct:
        """Build one deterministic Qdrant point with retrieval metadata."""
        point_id = str(
            uuid5(
                NAMESPACE_URL,
                f"{self._collection_name}:{document.id}:{chunk.chunk_index}",
            )
        )
        payload: dict[str, str | int | None] = {
            "document_id": document.id,
            "filename": document.filename,
            "original_filename": document.original_filename,
            "sha256": document.sha256,
            "content": chunk.content,
            "page": chunk.page,
            "section": chunk.section,
            "chunk_index": chunk.chunk_index,
        }
        return models.PointStruct(
            id=point_id,
            vector=list(vector),
            payload=payload,
        )


class QdrantRepository:
    """Persist and search document chunks using Qdrant Local mode."""

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        *,
        path: Path = DEFAULT_LOCAL_QDRANT_PATH,
        collection_name: str = DEFAULT_LOCAL_COLLECTION_NAME,
        client: QdrantClient | None = None,
    ) -> None:
        """Initialize local storage and read vector size from the model."""
        dimension = embedding_model.get_sentence_embedding_dimension()
        if dimension is None or dimension <= 0:
            raise ValueError("Embedding model must provide a positive dimension")
        self._dimension = dimension
        self._collection_name = collection_name
        self._client = client or QdrantClient(path=str(path))

    @property
    def vector_dimension(self) -> int:
        """Return the vector dimension read from the embedding model."""
        return self._dimension

    def create_collection(self) -> None:
        """Create the cosine-distance collection when it does not exist."""
        if self._client.collection_exists(self._collection_name):
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=self._dimension,
                distance=models.Distance.COSINE,
            ),
        )

    def upsert_chunks(
        self,
        chunks: Sequence[DomainChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Insert or update chunks and their corresponding vectors."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        self.create_collection()
        points = [
            self._build_local_point(chunk, vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        for offset in range(0, len(points), QDRANT_UPSERT_BATCH_SIZE):
            self._client.upsert(
                collection_name=self._collection_name,
                points=points[offset : offset + QDRANT_UPSERT_BATCH_SIZE],
                wait=True,
            )

    def delete_document(self, document_id: int) -> None:
        """Delete every stored chunk belonging to one document."""
        if not self._client.collection_exists(self._collection_name):
            return
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def search(
        self,
        vector: Sequence[float],
        limit: int = 10,
    ) -> list[RetrievalCandidate]:
        """Return cosine-ranked local chunk matches."""
        self._validate_vector(vector)
        if not self._client.collection_exists(self._collection_name):
            return []
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=list(vector),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [self._to_retrieval_candidate(point) for point in response.points]

    def close(self) -> None:
        """Close the local Qdrant storage client."""
        self._client.close()

    def _build_local_point(
        self,
        chunk: DomainChunk,
        vector: Sequence[float],
    ) -> models.PointStruct:
        """Build one local Qdrant point from a domain chunk."""
        if chunk.document_id is None:
            raise ValueError("document_id is required for Qdrant persistence")
        self._validate_vector(vector)
        point_id = str(
            uuid5(
                NAMESPACE_URL,
                f"{self._collection_name}:{chunk.document_id}:{chunk.id}",
            )
        )
        payload: dict[str, str | int | None] = {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "page": chunk.page,
            "section": chunk.section,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "token_count": chunk.token_count,
        }
        return models.PointStruct(
            id=point_id,
            vector=list(vector),
            payload=payload,
        )

    def _validate_vector(self, vector: Sequence[float]) -> None:
        """Reject vectors that do not match the embedding model dimension."""
        if len(vector) != self._dimension:
            raise ValueError(
                f"Expected vector dimension {self._dimension}, got {len(vector)}"
            )

    @staticmethod
    def _to_retrieval_candidate(point: models.ScoredPoint) -> RetrievalCandidate:
        """Convert one local Qdrant point into a retrieval candidate."""
        payload = point.payload or {}
        return RetrievalCandidate(
            document_id=int(payload["document_id"]),
            chunk_index=int(payload["chunk_index"]),
            content=str(payload["text"]),
            page=(int(payload["page"]) if payload.get("page") is not None else None),
            section=(
                str(payload["section"]) if payload.get("section") is not None else None
            ),
            score=float(point.score),
        )
