"""Shared embedding and vector-store dependencies."""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.repositories.qdrant import QdrantChunkRepository
from app.services.embedding import EmbeddingService, EmbeddingServiceUnavailableError
from app.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

EMBEDDING_UNAVAILABLE_MESSAGE = "Embedding model is unavailable"


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Return the process-wide CPU embedding service.

    Construction loads the encoder (downloading it on a first run), so it is the
    one dependency that can fail for purely operational reasons. The failure is
    translated here, at the boundary, because a ``lru_cache`` entry that raises
    is simply not stored -- the next request retries instead of caching the
    error forever.
    """
    try:
        return EmbeddingService()
    except Exception as exc:
        logger.exception("Embedding model could not be loaded")
        raise EmbeddingServiceUnavailableError(EMBEDDING_UNAVAILABLE_MESSAGE) from exc


def require_embedding_service(
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> EmbeddingService:
    """Return the encoder, refusing the request when it is unavailable.

    FastAPI resolves the injected encoder before the route body runs, so without
    this declaration a dependency that cannot be built escapes as an opaque 500
    instead of the 503 handled by ``embedding_unavailable_handler``.

    The already-resolved value is returned as-is. Calling
    ``get_embedding_service()`` again here would bypass
    ``app.dependency_overrides`` and load the real model even when a test has
    substituted it.
    """
    return embedding_service


@lru_cache
def get_qdrant_repository() -> QdrantChunkRepository:
    """Return the process-wide Qdrant chunk repository."""
    settings = get_settings()
    return QdrantChunkRepository(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection_name,
        score_threshold=settings.retrieval_min_score,
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Return the process-wide OpenAI-compatible LLM provider."""
    return LLMProvider(settings=get_settings())


EmbeddingDependency = Annotated[EmbeddingService, Depends(get_embedding_service)]
EmbeddingReadyDependency = Annotated[
    EmbeddingService,
    Depends(require_embedding_service),
]
QdrantDependency = Annotated[
    QdrantChunkRepository,
    Depends(get_qdrant_repository),
]
LLMDependency = Annotated[LLMProvider, Depends(get_llm_provider)]
