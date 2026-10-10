"""Conversation aggregate repository."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole


class ConversationRepository:
    """Persist conversations and their ordered messages."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self._session = session

    def create(self, *, user_id: int, title: str | None = None) -> Conversation:
        """Create a conversation inside the caller's transaction."""
        conversation = Conversation(user_id=user_id, title=title)
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def get_for_user(
        self,
        conversation_id: int,
        user_id: int,
    ) -> Conversation | None:
        """Return a conversation only when it belongs to the given user."""
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        return self._session.scalar(statement)

    def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int = 0,
    ) -> Sequence[Conversation]:
        """Return one page of a user's conversations in newest-first order."""
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return self._session.scalars(statement).all()

    def count_for_user(self, user_id: int) -> int:
        """Return how many conversations a user owns, ignoring pagination."""
        statement = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
        return int(self._session.scalar(statement) or 0)

    def rename(self, conversation: Conversation, title: str) -> Conversation:
        """Rename a conversation inside the caller's transaction."""
        conversation.title = title
        self._session.flush()
        return conversation

    def add_exchange(
        self,
        *,
        conversation_id: int,
        question: str,
        answer: str,
    ) -> tuple[Message, Message]:
        """Add one user and assistant message inside the caller's transaction."""
        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER.value,
            content=question,
        )
        assistant_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT.value,
            content=answer,
        )
        self._session.add_all((user_message, assistant_message))
        self._session.flush()
        return user_message, assistant_message

    def add_message(
        self,
        *,
        conversation_id: int,
        role: MessageRole,
        content: str,
    ) -> Message:
        """Create one message inside the caller's transaction."""
        message = Message(
            conversation_id=conversation_id,
            role=role.value,
            content=content,
        )
        self._session.add(message)
        self._session.flush()
        return message

    def list_messages(self, conversation_id: int) -> Sequence[Message]:
        """Return conversation messages in stable chronological order."""
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return self._session.scalars(statement).all()

    def list_recent_messages(
        self,
        conversation_id: int,
        limit: int,
    ) -> Sequence[Message]:
        """Return the newest messages of a conversation in chronological order.

        Only the newest rows are read, so a long conversation does not load its
        whole history just to build a follow-up question.
        """
        if limit <= 0:
            return []
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(reversed(self._session.scalars(statement).all()))

    def delete(self, conversation: Conversation) -> None:
        """Delete a conversation and its messages inside the caller's transaction."""
        self._session.execute(
            delete(Message).where(Message.conversation_id == conversation.id)
        )
        self._session.delete(conversation)
        self._session.flush()
