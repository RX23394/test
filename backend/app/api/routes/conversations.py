"""Authenticated conversation lifecycle endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import CurrentUser, SessionDependency
from app.repositories.conversation import ConversationRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
)
from app.schemas.response import ResponseModel
from app.services.conversation import ConversationNotFoundError, ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _service(session: SessionDependency) -> ConversationService:
    """Build a request-scoped conversation service."""
    return ConversationService(ConversationRepository(session))


def _not_found(error: ConversationNotFoundError) -> HTTPException:
    """Return a non-leaking conversation-not-found response."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Conversation not found",
    )


@router.get("", response_model=ResponseModel[list[ConversationResponse]])
def list_conversations(
    current_user: CurrentUser,
    session: SessionDependency,
) -> ResponseModel[list[ConversationResponse]]:
    """List the current user's conversations newest first."""
    conversations = _service(session).list(current_user.id)
    return ResponseModel(
        status="ok",
        data=[ConversationResponse.model_validate(item) for item in conversations],
    )


@router.post("", response_model=ResponseModel[ConversationResponse])
def create_conversation(
    payload: ConversationCreate,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ResponseModel[ConversationResponse]:
    """Create a conversation owned by the current user."""
    conversation = _service(session).create(current_user.id, payload.title)
    return ResponseModel(
        status="ok",
        data=ConversationResponse.model_validate(conversation),
    )


@router.get(
    "/{conversation_id}",
    response_model=ResponseModel[ConversationDetailResponse],
)
def get_conversation(
    conversation_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ResponseModel[ConversationDetailResponse]:
    """Return one owned conversation and its ordered messages."""
    try:
        detail = _service(session).get(conversation_id, current_user.id)
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from exc
    return ResponseModel(
        status="ok",
        data=ConversationDetailResponse(
            conversation=ConversationResponse.model_validate(detail.conversation),
            messages=[MessageResponse.model_validate(item) for item in detail.messages],
        ),
    )


@router.patch("/{conversation_id}", response_model=ResponseModel[ConversationResponse])
def rename_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ResponseModel[ConversationResponse]:
    """Rename one owned conversation."""
    try:
        conversation = _service(session).rename(
            conversation_id,
            current_user.id,
            payload.title,
        )
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from exc
    return ResponseModel(
        status="ok",
        data=ConversationResponse.model_validate(conversation),
    )


@router.delete("/{conversation_id}", response_model=ResponseModel[bool])
def delete_conversation(
    conversation_id: int,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ResponseModel[bool]:
    """Delete one owned conversation and all messages."""
    try:
        _service(session).delete(conversation_id, current_user.id)
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from exc
    return ResponseModel(status="ok", data=True)
