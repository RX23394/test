"""Conversation and message lifecycle orchestration."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.repositories.conversation import ConversationRepository


class ConversationNotFoundError(LookupError):
    """Raised when a conversation is absent or belongs to another user."""


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    """One conversation and its chronologically ordered messages."""

    conversation: Conversation
    messages: list[Message]


class ConversationService:
    """Manage user-owned conversations and their messages."""

    def __init__(self, repository: ConversationRepository) -> None:
        """Initialize the service with its aggregate repository."""
        self._repository = repository

    def create(
        self,
        user_id: int,
        title: str | None = None,
    ) -> Conversation:
        """Create and return a conversation owned by a user."""
        self._validate_id(user_id, "user_id")
        normalized_title = self._normalize_title(title)
        return self._repository.create(
            user_id=user_id,
            title=normalized_title,
        )

    def get(self, conversation_id: int, user_id: int) -> ConversationDetail:
        """Return a user-owned conversation with all ordered messages."""
        conversation = self._require_conversation(conversation_id, user_id)
        messages = list(self._repository.list_messages(conversation.id))
        return ConversationDetail(conversation=conversation, messages=messages)

    def list(self, user_id: int) -> Sequence[Conversation]:
        """Return all conversations owned by a user, newest first."""
        self._validate_id(user_id, "user_id")
        return self._repository.list_for_user(user_id)

    def rename(
        self,
        conversation_id: int,
        user_id: int,
        title: str,
    ) -> Conversation:
        """Rename a user-owned conversation."""
        conversation = self._require_conversation(conversation_id, user_id)
        normalized_title = self._normalize_title(title)
        if normalized_title is None:
            raise ValueError("title must not be empty")
        return self._repository.rename(conversation, normalized_title)

    def add_exchange(
        self,
        conversation_id: int,
        user_id: int,
        question: str,
        answer: str,
    ) -> tuple[Message, Message]:
        """Persist a completed user and assistant exchange atomically."""
        conversation = self._require_conversation(conversation_id, user_id)
        normalized_question = question.strip()
        normalized_answer = answer.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        if not normalized_answer:
            raise ValueError("answer must not be empty")
        return self._repository.add_exchange(
            conversation_id=conversation.id,
            question=normalized_question,
            answer=normalized_answer,
        )

    def add_message(
        self,
        conversation_id: int,
        user_id: int,
        role: MessageRole | str,
        content: str,
    ) -> Message:
        """Validate and save a user or assistant message."""
        conversation = self._require_conversation(conversation_id, user_id)
        normalized_role = self._normalize_role(role)
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("content must not be empty")
        return self._repository.add_message(
            conversation_id=conversation.id,
            role=normalized_role,
            content=normalized_content,
        )

    def delete(self, conversation_id: int, user_id: int) -> None:
        """Delete a user-owned conversation and all of its messages."""
        conversation = self._require_conversation(conversation_id, user_id)
        self._repository.delete(conversation)

    def _require_conversation(
        self,
        conversation_id: int,
        user_id: int,
    ) -> Conversation:
        """Return an owned conversation or raise a non-leaking error."""
        self._validate_id(conversation_id, "conversation_id")
        self._validate_id(user_id, "user_id")
        conversation = self._repository.get_for_user(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} does not exist"
            )
        return conversation

    @staticmethod
    def _validate_id(value: int, field: str) -> None:
        """Require a positive database identifier."""
        if value <= 0:
            raise ValueError(f"{field} must be greater than zero")

    @staticmethod
    def _normalize_title(title: str | None) -> str | None:
        """Normalize an optional title and enforce the model limit."""
        if title is None:
            return None
        normalized_title = title.strip()
        if not normalized_title:
            return None
        if len(normalized_title) > 255:
            raise ValueError("title must not exceed 255 characters")
        return normalized_title

    @staticmethod
    def _normalize_role(role: MessageRole | str) -> MessageRole:
        """Return a supported user or assistant role."""
        try:
            return MessageRole(role)
        except ValueError as exc:
            raise ValueError("role must be user or assistant") from exc
