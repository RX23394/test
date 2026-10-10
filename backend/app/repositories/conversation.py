"""Conversation aggregate repository."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole


class ConversationRepository:
    """Persist conversations and their ordered messages."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self._session = session

    def create(self, *, user_id: int, title: str | None = None) -> Conversation:
        """Create and persist a conversation."""
        conversation = Conversation(user_id=user_id, title=title)
        self._session.add(conversation)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        self._session.refresh(conversation)
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

    def list_for_user(self, user_id: int) -> Sequence[Conversation]:
        """Return one user's conversations in newest-first order."""
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )
        return self._session.scalars(statement).all()

    def rename(self, conversation: Conversation, title: str) -> Conversation:
        """Persist a new title for a conversation."""
        conversation.title = title
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        self._session.refresh(conversation)
        return conversation

    def add_exchange(
        self,
        *,
        conversation_id: int,
        question: str,
        answer: str,
    ) -> tuple[Message, Message]:
        """Persist one user and assistant message atomically."""
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
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return user_message, assistant_message

    def add_message(
        self,
        *,
        conversation_id: int,
        role: MessageRole,
        content: str,
    ) -> Message:
        """Create and persist one message in a conversation."""
        message = Message(
            conversation_id=conversation_id,
            role=role.value,
            content=content,
        )
        self._session.add(message)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        self._session.refresh(message)
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
        """Delete a conversation and all of its messages atomically."""
        try:
            self._session.execute(
                delete(Message).where(Message.conversation_id == conversation.id)
            )
            self._session.delete(conversation)
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
