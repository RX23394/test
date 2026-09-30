"""Authenticated retrieval-only search endpoint."""

import logging

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import CurrentUser, SessionDependency
from app.rag.dependencies import EmbeddingDependency, QdrantDependency
from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.schemas.response import ResponseModel
from app.schemas.search import SearchApiResult, SearchRequest
from app.services.keyword_search import KeywordSearchService
from app.services.search import SearchService
from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post(
    "",
    response_model=ResponseModel[list[SearchApiResult]],
    response_model_exclude_none=True,
)
def search_documents(
    payload: SearchRequest,
    current_user: CurrentUser,
    session: SessionDependency,
    embedding_service: EmbeddingDependency,
    qdrant_repository: QdrantDependency,
) -> ResponseModel[list[SearchApiResult]]:
    """Return retrieval results without answer generation."""
    del current_user
    service = SearchService(
        vector_search_service=VectorSearchService(
            embedding_service,
            qdrant_repository,
        ),
        keyword_search_service=KeywordSearchService(FtsChunkRepository(session)),
    )
    try:
        results = service.search(payload.query)
    except Exception as exc:
        logger.exception("Search retrieval failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service is unavailable",
        ) from exc

    documents = DocumentRepository(session).get_by_ids(
        [result.document for result in results]
    )
    response_results = [
        SearchApiResult(
            document=documents[result.document].original_filename,
            page=result.page,
            section=result.section,
            content=result.chunk,
            score=result.score,
        )
        for result in results
        if result.document in documents
    ]
    return ResponseModel(status="ok", data=response_results)
