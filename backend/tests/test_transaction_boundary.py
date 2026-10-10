"""Tests for the transaction boundary introduced by moving commits out of repositories.

Repositories only flush, ``get_db`` commits one request at a time, and the few
units of work that live outside a request (background indexing, streamed-answer
persistence, CLI commands) commit on their own. These tests pin that contract so
a future repository cannot quietly start committing again.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.db import session as session_module
from app.db.session import get_db
from app.repositories.user import UserRepository


def test_repository_writes_are_discarded_by_a_rollback(
    session_factory: sessionmaker[Session],
) -> None:
    """A repository write is not committed until the caller commits."""
    with session_factory() as session:
        user_id = (
            UserRepository(session)
            .create(username="rollback-user", password_hash="hashed-password")
            .id
        )
        session.rollback()

    with session_factory() as session:
        assert UserRepository(session).get_by_id(user_id) is None


def test_get_db_commits_a_successful_request(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """Resuming the request generator persists everything it wrote."""
    monkeypatch.setattr(session_module, "SessionFactory", session_factory)
    generator: Iterator[Session] = get_db()

    session = next(generator)
    user_id = (
        UserRepository(session)
        .create(username="committed-user", password_hash="hashed-password")
        .id
    )
    with pytest.raises(StopIteration):
        next(generator)

    with session_factory() as session:
        assert UserRepository(session).get_by_id(user_id) is not None


def test_get_db_rolls_back_a_failed_request(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """An exception raised through the request rolls its writes back."""
    monkeypatch.setattr(session_module, "SessionFactory", session_factory)
    generator: Iterator[Session] = get_db()

    session = next(generator)
    user_id = (
        UserRepository(session)
        .create(username="failed-user", password_hash="hashed-password")
        .id
    )
    with pytest.raises(RuntimeError, match="handler failed"):
        generator.throw(RuntimeError("handler failed"))

    with session_factory() as session:
        assert UserRepository(session).get_by_id(user_id) is None
