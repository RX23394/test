"""Shared embedding and vector-store dependencies."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.repositories.qdrant import QdrantChunkRepository
from app.services.embedding import EmbeddingService
from app.services.llm_provider import LLMProvider


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Return the process-wide CPU embedding service."""
    return EmbeddingService()


@lru_cache
def get_qdrant_repository() -> QdrantChunkRepository:
    """Return the process-wide Qdrant chunk repository."""
    settings = get_settings()
    return QdrantChunkRepository(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection_name,
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Return the process-wide OpenAI-compatible LLM provider."""
    return LLMProvider(settings=get_settings())


EmbeddingDependency = Annotated[EmbeddingService, Depends(get_embedding_service)]
QdrantDependency = Annotated[
    QdrantChunkRepository,
    Depends(get_qdrant_repository),
]
LLMDependency = Annotated[LLMProvider, Depends(get_llm_provider)]
