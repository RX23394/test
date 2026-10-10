"""Authenticated citation-grounded streaming endpoint."""

import logging
import math
from collections.abc import Callable, Iterator, Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import CurrentUser, SessionDependency
from app.core.config import get_settings
from app.core.rate_limit import (
    FixedWindowRateLimiter,
    get_chat_rate_limiter,
)
from app.db.session import SessionFactoryDependency
from app.rag.dependencies import EmbeddingDependency, LLMDependency, QdrantDependency
from app.repositories.conversation import ConversationRepository
from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.schemas.chat import ChatRequest, CitationSource
from app.schemas.response import ResponseModel
from app.services.citation_resolver import (
    Citation,
    CitationResolutionError,
    CitationResolver,
)
from app.services.conversation import ConversationNotFoundError, ConversationService
from app.services.llm_errors import (
    LLM_API_ERROR_MESSAGE,
    LLM_TIMEOUT_MESSAGE,
    TOKEN_LIMIT_MESSAGE,
    LLMAPIError,
    LLMTimeoutError,
    LLMTokenLimitError,
)
from app.services.llm_provider import LLMProvider
from app.services.prompt_builder import (
    DEFAULT_HISTORY_TOKEN_BUDGET,
    INSUFFICIENT_KNOWLEDGE_RESPONSE,
    PromptBuilder,
    PromptHistoryMessage,
)
from app.services.retrieval_query import build_retrieval_query
from app.services.search import HybridSearchError, HybridSearchService

logger = logging.getLogger(__name__)
StreamingEventName = Literal["token", "citation", "done", "error"]
CHAT_PERSISTENCE_ERROR_MESSAGE = "Conversation could not be saved"
CHAT_RATE_LIMIT_MESSAGE = "Too many chat requests, try again later"
ChatRateLimiterDependency = Annotated[
    FixedWindowRateLimiter,
    Depends(get_chat_rate_limiter),
]

router = APIRouter(prefix="/api/chat", tags=["chat"])


def serialize_sse[DataT](
    event: StreamingEventName,
    payload: ResponseModel[DataT],
) -> str:
    """Serialize one uniform response envelope as a server-sent event."""
    data = payload.model_dump_json(exclude_none=True)
    return f"event: {event}\ndata: {data}\n\n"


def _get_llm_error_message(error: Exception) -> str:
    """Map application LLM failures to stable client-safe messages."""
    if isinstance(error, LLMTimeoutError):
        return LLM_TIMEOUT_MESSAGE
    if isinstance(error, LLMTokenLimitError):
        return TOKEN_LIMIT_MESSAGE
    if isinstance(error, LLMAPIError):
        return LLM_API_ERROR_MESSAGE
    return LLM_API_ERROR_MESSAGE


def stream_chat_events(
    query: str,
    sources: list[CitationSource],
    citations: list[Citation],
    llm_provider: LLMProvider,
    on_complete: Callable[[str], None] | None = None,
    *,
    history: Sequence[PromptHistoryMessage] = (),
    history_token_budget: int = DEFAULT_HISTORY_TOKEN_BUDGET,
) -> Iterator[str]:
    """Yield source, text delta, completion, or streaming error events."""
    if not sources:
        if not _persist_completed_answer(
            on_complete,
            INSUFFICIENT_KNOWLEDGE_RESPONSE,
        ):
            yield _persistence_error_event()
            return
        yield serialize_sse(
            "token",
            ResponseModel(
                status="ok",
                data=INSUFFICIENT_KNOWLEDGE_RESPONSE,
            ),
        )
        yield serialize_sse(
            "citation",
            ResponseModel(status="ok", data=[]),
        )
        yield serialize_sse(
            "done",
            ResponseModel[None](status="ok"),
        )
        return

    answer_parts: list[str] = []
    try:
        messages = PromptBuilder(history_token_budget).build_from_sources(
            query,
            sources,
            history,
        )
        for content in llm_provider.stream_chat(messages):
            answer_parts.append(content)
            yield serialize_sse(
                "token",
                ResponseModel(
                    status="ok",
                    data=content,
                ),
            )
    except Exception as exc:
        logger.exception("OpenAI-compatible streaming failed")
        error_message = _get_llm_error_message(exc)
        yield serialize_sse(
            "error",
            ResponseModel[None](
                status="error",
                message=error_message,
            ),
        )
        return
    if not _persist_completed_answer(on_complete, "".join(answer_parts)):
        yield _persistence_error_event()
        return
    yield serialize_sse(
        "citation",
        ResponseModel(
            status="ok",
            data=citations,
        ),
    )
    yield serialize_sse(
        "done",
        ResponseModel[None](status="ok"),
    )


def persist_stream_exchange(
    session_factory: sessionmaker[Session],
    *,
    conversation_id: int,
    user_id: int,
    question: str,
    answer: str,
) -> None:
    """Persist one completed exchange using a session this call owns.

    The request-scoped session is already closed by the time a streaming
    response body is consumed, because ``get_db`` exits when the request
    returns. Writing through that closed session only appeared to work: it made
    SQLAlchemy reopen a transaction outside the request boundary, leaving the
    write with no rollback path. Owning a short-lived session keeps the write
    inside a normal transaction.
    """
    with session_factory() as write_session:
        ConversationService(ConversationRepository(write_session)).add_exchange(
            conversation_id,
            user_id,
            question,
            answer,
        )


def _persist_completed_answer(
    on_complete: Callable[[str], None] | None,
    answer: str,
) -> bool:
    """Persist a completed answer and report whether it succeeded."""
    if on_complete is None:
        return True
    try:
        on_complete(answer)
    except Exception:
        logger.exception("Completed chat exchange could not be persisted")
        return False
    return True


def _persistence_error_event() -> str:
    """Return the terminal SSE event used when conversation storage fails."""
    return serialize_sse(
        "error",
        ResponseModel[None](
            status="error",
            message=CHAT_PERSISTENCE_ERROR_MESSAGE,
        ),
    )


def create_streaming_response(events: Iterator[str]) -> StreamingResponse:
    """Wrap an SSE iterator in a non-buffered FastAPI response."""
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stream", response_class=StreamingResponse)
def stream_chat(
    payload: ChatRequest,
    current_user: CurrentUser,
    session: SessionDependency,
    embedding_service: EmbeddingDependency,
    qdrant_repository: QdrantDependency,
    llm_provider: LLMDependency,
    session_factory: SessionFactoryDependency,
    chat_limiter: ChatRateLimiterDependency,
) -> StreamingResponse:
    """Retrieve Top8 sources and stream a citation-grounded answer."""
    rate_limit_key = f"user:{current_user.id}"
    if not chat_limiter.allow(rate_limit_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=CHAT_RATE_LIMIT_MESSAGE,
            headers={
                "Retry-After": str(
                    max(1, math.ceil(chat_limiter.retry_after(rate_limit_key)))
                )
            },
        )
    settings = get_settings()
    conversation_service = ConversationService(ConversationRepository(session))
    try:
        conversation_service.get(payload.conversation_id, current_user.id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc

    # One turn is a question plus its answer; only the newest window is read.
    history = conversation_service.recent_messages(
        payload.conversation_id,
        current_user.id,
        limit=settings.chat_history_turns * 2,
    )
    search_service = HybridSearchService(
        embedding_provider=embedding_service,
        vector_repository=qdrant_repository,
        text_repository=FtsChunkRepository(session),
        min_vector_score=settings.retrieval_min_score,
    )
    try:
        results = search_service.search(
            build_retrieval_query(
                payload.message,
                history,
                turns=settings.chat_history_turns,
            )
        )
    except HybridSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service is unavailable",
        ) from exc
    try:
        citations = CitationResolver(DocumentRepository(session)).resolve(results)
    except CitationResolutionError as exc:
        logger.exception("Database citation resolution failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Citation sources are unavailable",
        ) from exc
    sources = [
        CitationSource.from_search_result(result, index)
        for index, result in enumerate(results, start=1)
    ]

    def persist_exchange(answer: str) -> None:
        """Persist a completed exchange through a session this call owns."""
        persist_stream_exchange(
            session_factory,
            conversation_id=payload.conversation_id,
            user_id=current_user.id,
            question=payload.message,
            answer=answer,
        )

    return create_streaming_response(
        stream_chat_events(
            payload.message,
            sources,
            citations,
            llm_provider,
            persist_exchange,
            history=history,
            history_token_budget=settings.chat_history_max_tokens,
        )
    )
