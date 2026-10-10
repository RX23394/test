"""Qdrant repository for document chunk vectors."""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.models.document import Document
from app.schemas.chunk import Chunk
from app.schemas.search import RetrievalCandidate
from app.services.embedding import EMBEDDING_DIMENSION

QDRANT_UPSERT_BATCH_SIZE = 100


class QdrantChunkRepository:
    """Replace and persist document chunk vectors in Qdrant."""

    def __init__(
        self,
        *,
        url: str,
        collection_name: str,
        api_key: str | None = None,
        client: QdrantClient | None = None,
        score_threshold: float | None = None,
    ) -> None:
        """Initialize the repository with Qdrant connection settings."""
        self._collection_name = collection_name
        self._client = client or QdrantClient(url=url, api_key=api_key)
        self._score_threshold = score_threshold

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
        """Return cosine-ranked chunk candidates above the similarity floor."""
        if not self._client.collection_exists(self._collection_name):
            return []
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=list(vector),
            limit=limit,
            with_payload=True,
            with_vectors=False,
            score_threshold=self._score_threshold,
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
