"""Tests for the administrator creation command."""

import sys

import pytest
from sqlalchemy.orm import Session, sessionmaker

import app.cli.create_admin as create_admin_module
from app.repositories.user import UserRepository


def test_create_admin_command(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """The interactive command creates an administrator through the repository."""

    def fake_input(prompt: str) -> str:
        """Return a test username for the interactive prompt."""
        del prompt
        return "first-admin"

    def fake_getpass(prompt: str) -> str:
        """Return a test password for both hidden password prompts."""
        del prompt
        return "test-admin-password"

    monkeypatch.setattr(sys, "argv", ["create_admin"])
    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(create_admin_module.getpass, "getpass", fake_getpass)
    monkeypatch.setattr(create_admin_module, "SessionFactory", session_factory)

    create_admin_module.main()

    with session_factory() as session:
        admin = UserRepository(session).get_by_username("first-admin")
    assert admin is not None
    assert admin.is_admin is True
    assert admin.password_hash != "test-admin-password"
