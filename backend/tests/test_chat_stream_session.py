"""The streamed chat exchange must be persisted by a session it owns.

``get_db`` closes its session when the request returns, but a ``StreamingResponse``
body is consumed afterwards. The original implementation persisted the exchange
through that closed request session; SQLAlchemy silently reopened a transaction
on it, so the write happened outside the request transaction boundary with no
rollback path. These tests pin the corrected behaviour.
"""

from collections.abc import Iterator
from inspect import signature
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.chat import persist_stream_exchange, stream_chat
from app.db.base import Base
from app.db.schema import current_chunk_index_ddl, current_document_chunks_fts_ddl
from app.db.session import get_session_factory
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.user import User


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Provide an isolated in-memory database with the search tables."""
    created = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(created)
    with created.begin() as connection:
        connection.exec_driver_sql(current_document_chunks_fts_ddl())
        connection.exec_driver_sql(current_chunk_index_ddl())
    yield created
    Base.metadata.drop_all(created)
    created.dispose()


@pytest.fixture
def conversation_ids(engine: Engine) -> tuple[int, int]:
    """Create a user and a conversation, returning both identifiers."""
    factory: sessionmaker[Session] = sessionmaker(bind=engine)
    with factory() as session:
        user = User(
            username="streamer",
            password_hash="hash",
            is_admin=False,
            is_active=True,
        )
        session.add(user)
        session.flush()
        conversation = Conversation(user_id=user.id, title="chat")
        session.add(conversation)
        session.commit()
        return user.id, conversation.id


def test_persist_stream_exchange_opens_its_own_session(
    engine: Engine,
    conversation_ids: tuple[int, int],
) -> None:
    """Persistence must create a session rather than reuse the request's."""
    user_id, conversation_id = conversation_ids
    factory: sessionmaker[Session] = sessionmaker(bind=engine)
    created_sessions: list[Session] = []

    @event.listens_for(factory, "after_begin")
    def record(session: Session, transaction: object, connection: object) -> None:
        del transaction, connection
        created_sessions.append(session)

    # Simulate the request lifecycle: the request session is closed before the
    # streaming body runs. A closed session is unusable for this write.
    request_session = factory()
    request_session.close()
    assert request_session.in_transaction() is False

    persist_stream_exchange(
        factory,
        conversation_id=conversation_id,
        user_id=user_id,
        question="What is OSPF?",
        answer="OSPF is a link-state protocol [S1].",
    )

    assert created_sessions, "persistence did not open its own session"

    with factory() as session:
        messages = session.query(Message).order_by(Message.id).all()
        assert [(message.role, message.content) for message in messages] == [
            (MessageRole.USER, "What is OSPF?"),
            (MessageRole.ASSISTANT, "OSPF is a link-state protocol [S1]."),
        ]


def test_persist_stream_exchange_closes_its_session(
    engine: Engine,
    conversation_ids: tuple[int, int],
) -> None:
    """The owned session must be closed, not leaked, after the write."""
    user_id, conversation_id = conversation_ids
    factory: sessionmaker[Session] = sessionmaker(bind=engine)
    live_sessions: list[Session] = []
    closed_sessions: list[Session] = []

    @event.listens_for(factory, "after_begin")
    def record_begin(session: Session, transaction: object, connection: object) -> None:
        del transaction, connection
        live_sessions.append(session)

    @event.listens_for(factory, "after_transaction_end")
    def record_end(session: Session, transaction: object) -> None:
        del transaction
        closed_sessions.append(session)

    persist_stream_exchange(
        factory,
        conversation_id=conversation_id,
        user_id=user_id,
        question="question",
        answer="answer",
    )

    assert live_sessions
    assert set(live_sessions).issubset(set(closed_sessions))


def test_persist_stream_exchange_rejects_a_foreign_conversation(
    engine: Engine,
    conversation_ids: tuple[int, int],
) -> None:
    """Writing to another user's conversation must fail loudly."""
    _, conversation_id = conversation_ids
    factory: sessionmaker[Session] = sessionmaker(bind=engine)
    with factory() as session:
        other = User(
            username="other",
            password_hash="hash",
            is_admin=False,
            is_active=True,
        )
        session.add(other)
        session.commit()
        other_id = other.id

    with pytest.raises(LookupError):
        persist_stream_exchange(
            factory,
            conversation_id=conversation_id,
            user_id=other_id,
            question="question",
            answer="answer",
        )

    with factory() as session:
        assert session.query(Message).count() == 0


def test_streaming_route_accepts_an_injectable_session_factory() -> None:
    """The route must resolve its factory through a dependency.

    Without the parameter the route can only reach the module-level
    ``SessionFactory``, which points at the production database and cannot be
    redirected by the test suite.
    """
    assert "session_factory" in signature(stream_chat).parameters


def test_session_factory_dependency_is_overridable() -> None:
    """The factory dependency must exist and be importable for overrides."""
    assert callable(get_session_factory)


def test_backend_root_is_importable() -> None:
    """Guard against the test module drifting away from the backend root."""
    assert (Path(__file__).resolve().parents[1] / "alembic.ini").is_file()
