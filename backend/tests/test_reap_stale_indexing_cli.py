"""Tests for the stale indexing lease sweep command."""

import sys
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

import app.cli.reap_stale_indexing as reap_module
from app.models.document import DocumentStatus
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository


def create_claimed_document(
    session: Session,
    *,
    username: str,
    sha256: str,
    claimed_minutes_ago: int,
) -> int:
    """Create a document whose indexing lease started in the past."""
    user = UserRepository(session).create(
        username=username,
        password_hash="hashed-password",
    )
    repository = DocumentRepository(session)
    document = repository.create(
        filename=f"{username}.md",
        original_filename=f"{username}.md",
        sha256=sha256,
        file_size=32,
        uploader_id=user.id,
    )
    claimed = repository.claim_for_indexing(document.id, f"job-{username}")
    assert claimed is not None
    claimed.indexing_started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        minutes=claimed_minutes_ago
    )
    session.commit()
    return document.id


def test_reap_command_resets_only_expired_leases(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """The sweep fails stale documents and leaves running jobs untouched."""
    with session_factory() as session:
        stale_id = create_claimed_document(
            session,
            username="stale-worker",
            sha256="a" * 64,
            claimed_minutes_ago=30,
        )
        live_id = create_claimed_document(
            session,
            username="live-worker",
            sha256="b" * 64,
            claimed_minutes_ago=1,
        )

    monkeypatch.setattr(sys, "argv", ["reap_stale_indexing"])
    monkeypatch.setattr(reap_module, "SessionFactory", session_factory)

    reap_module.main()

    with session_factory() as session:
        repository = DocumentRepository(session)
        stale = repository.get_by_id(stale_id)
        live = repository.get_by_id(live_id)
    assert stale is not None
    assert live is not None
    assert stale.status is DocumentStatus.FAILED
    assert stale.indexing_job_id is None
    assert live.status is DocumentStatus.PROCESSING
    assert live.indexing_job_id == "job-live-worker"


def test_reap_command_accepts_an_explicit_lease(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """An operator can tighten the lease window on the command line."""
    with session_factory() as session:
        document_id = create_claimed_document(
            session,
            username="recent-worker",
            sha256="c" * 64,
            claimed_minutes_ago=5,
        )

    monkeypatch.setattr(
        sys,
        "argv",
        ["reap_stale_indexing", "--lease-seconds", "60"],
    )
    monkeypatch.setattr(reap_module, "SessionFactory", session_factory)

    reap_module.main()

    with session_factory() as session:
        document = DocumentRepository(session).get_by_id(document_id)
    assert document is not None
    assert document.status is DocumentStatus.FAILED
