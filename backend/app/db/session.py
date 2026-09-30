"""SQLAlchemy engine and session management."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.schema import SQLITE_FOREIGN_KEYS_PRAGMA

settings = get_settings()

engine: Engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionFactory: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(
    dbapi_connection: object,
    connection_record: object,
) -> None:
    """Enable SQLite foreign key enforcement for every new connection.

    SQLite defaults to ``PRAGMA foreign_keys=OFF``, which silently disables
    every ``ON DELETE CASCADE`` declared by the models. The listener is bound to
    the ``Engine`` class so that engines created elsewhere, including the test
    fixtures, share the same guarantee.
    """
    del connection_record
    if not hasattr(dbapi_connection, "cursor"):
        return
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute(SQLITE_FOREIGN_KEYS_PRAGMA)
    finally:
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    with SessionFactory() as session:
        yield session


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory used for work that outlives a request."""
    return SessionFactory


# Allows tests to redirect work that outlives a request, such as persisting a
# streamed answer, to the same database the request itself used.
SessionFactoryDependency = Annotated[
    sessionmaker[Session],
    Depends(get_session_factory),
]
