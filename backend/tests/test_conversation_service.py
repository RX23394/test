"""Tests for conversation and message lifecycle persistence."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.services.conversation import (
    ConversationNotFoundError,
    ConversationService,
)


def create_user(session: Session, username: str) -> int:
    """Persist a user and return its identifier."""
    user = UserRepository(session).create(
        username=username,
        password_hash="test-password-hash",
    )
    return user.id


def test_conversation_service_creates_and_lists_only_owned_conversations(
    session_factory: sessionmaker[Session],
) -> None:
    """Creation normalizes titles and listing enforces user ownership."""
    with session_factory() as session:
        first_user_id = create_user(session, "conversation-owner")
        second_user_id = create_user(session, "other-owner")
        service = ConversationService(ConversationRepository(session))

        first = service.create(first_user_id, "  Network Study  ")
        second = service.create(first_user_id)
        other = service.create(second_user_id, "Other conversation")

        assert first.user_id == first_user_id
        assert first.title == "Network Study"
        assert second.title is None
        assert [item.id for item in service.list(first_user_id)] == [
            second.id,
            first.id,
        ]
        assert [item.id for item in service.list(second_user_id)] == [other.id]


def test_conversation_service_returns_only_the_newest_messages(
    session_factory: sessionmaker[Session],
) -> None:
    """The follow-up window is bounded, ordered, and ownership-checked."""
    with session_factory() as session:
        user_id = create_user(session, "recent-message-owner")
        other_user_id = create_user(session, "recent-message-other")
        service = ConversationService(ConversationRepository(session))
        conversation = service.create(user_id, "OSPF")
        for index in range(3):
            service.add_message(
                conversation.id,
                user_id,
                MessageRole.USER,
                f"question {index}",
            )
            service.add_message(
                conversation.id,
                user_id,
                MessageRole.ASSISTANT,
                f"answer {index}",
            )

        recent = service.recent_messages(conversation.id, user_id, limit=3)

        assert [message.content for message in recent] == [
            "answer 1",
            "question 2",
            "answer 2",
        ]
        assert service.recent_messages(conversation.id, user_id, limit=0) == []
        with pytest.raises(ConversationNotFoundError):
            service.recent_messages(conversation.id, other_user_id, limit=3)


def test_conversation_service_saves_user_and_assistant_messages_in_order(
    session_factory: sessionmaker[Session],
) -> None:
    """Both supported roles persist and query in chronological order."""
    with session_factory() as session:
        user_id = create_user(session, "message-owner")
        service = ConversationService(ConversationRepository(session))
        conversation = service.create(user_id, "OSPF")

        user_message = service.add_message(
            conversation.id,
            user_id,
            MessageRole.USER,
            "  What is OSPF?  ",
        )
        assistant_message = service.add_message(
            conversation.id,
            user_id,
            "assistant",
            "OSPF is a link-state protocol.",
        )
        detail = service.get(conversation.id, user_id)

        assert detail.conversation.id == conversation.id
        assert [message.id for message in detail.messages] == [
            user_message.id,
            assistant_message.id,
        ]
        assert [message.role for message in detail.messages] == [
            "user",
            "assistant",
        ]
        assert detail.messages[0].content == "What is OSPF?"


def test_conversation_service_rejects_invalid_messages_and_cross_user_access(
    session_factory: sessionmaker[Session],
) -> None:
    """Unsupported roles, blank content, and foreign ownership are rejected."""
    with session_factory() as session:
        owner_id = create_user(session, "secure-owner")
        other_user_id = create_user(session, "secure-other")
        service = ConversationService(ConversationRepository(session))
        conversation = service.create(owner_id)

        with pytest.raises(ValueError, match="role must be user or assistant"):
            service.add_message(
                conversation.id,
                owner_id,
                "system",
                "Hidden instruction",
            )
        with pytest.raises(ValueError, match="content must not be empty"):
            service.add_message(
                conversation.id,
                owner_id,
                MessageRole.USER,
                "   ",
            )
        with pytest.raises(ConversationNotFoundError):
            service.get(conversation.id, other_user_id)
        with pytest.raises(ConversationNotFoundError):
            service.add_message(
                conversation.id,
                other_user_id,
                MessageRole.USER,
                "Unauthorized",
            )
        with pytest.raises(ConversationNotFoundError):
            service.delete(conversation.id, other_user_id)

        assert service.get(conversation.id, owner_id).messages == []


def test_conversation_service_deletes_conversation_and_messages(
    session_factory: sessionmaker[Session],
) -> None:
    """Deleting an owned conversation removes its persisted messages."""
    with session_factory() as session:
        user_id = create_user(session, "delete-owner")
        service = ConversationService(ConversationRepository(session))
        conversation = service.create(user_id)
        message = service.add_message(
            conversation.id,
            user_id,
            MessageRole.ASSISTANT,
            "Stored answer",
        )
        conversation_id = conversation.id
        message_id = message.id

        service.delete(conversation_id, user_id)

        assert session.get(Conversation, conversation_id) is None
        assert session.get(Message, message_id) is None
        assert service.list(user_id) == []
        with pytest.raises(ConversationNotFoundError):
            service.get(conversation_id, user_id)


def test_conversation_service_validates_ids_and_title_length(
    session_factory: sessionmaker[Session],
) -> None:
    """Invalid identifiers and overlong titles fail before persistence."""
    with session_factory() as session:
        service = ConversationService(ConversationRepository(session))

        with pytest.raises(ValueError, match="user_id must be greater than zero"):
            service.create(0)
        with pytest.raises(ValueError, match="title must not exceed 255"):
            service.create(1, "x" * 256)
        with pytest.raises(
            ValueError,
            match="conversation_id must be greater than zero",
        ):
            service.get(0, 1)
