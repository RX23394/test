"""Shared backend test fixtures."""

from collections.abc import AsyncIterator, Iterator
from types import TracebackType

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.core.config import get_settings
from app.core.rate_limit import (
    FixedWindowRateLimiter,
    get_chat_rate_limiter,
    get_login_rate_limiter,
)
from app.db.base import Base
from app.db.schema import current_search_index_ddl, drop_search_index_ddl
from app.db.session import get_db, get_session_factory
from app.main import app

loaded_model_types = (
    models.User,
    models.Conversation,
    models.Document,
    models.Message,
)


class CommittingSession(Session):
    """Session whose context manager commits, mirroring the request boundary.

    Production commits once per request in ``get_db``; repositories only flush.
    A test block that drives repositories directly therefore has to persist its
    work the same way a request would, instead of relying on each repository
    call committing on its own.
    """

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit a successful block before the session is closed."""
        try:
            if exc_type is None:
                self.commit()
        finally:
            super().__exit__(exc_type, exc_value, traceback)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    """Provide a session factory backed by an isolated in-memory database."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for statement in current_search_index_ddl():
            connection.exec_driver_sql(statement)
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=CommittingSession,
    )
    yield factory
    with engine.begin() as connection:
        for statement in drop_search_index_ddl():
            connection.exec_driver_sql(statement)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest_asyncio.fixture
async def client(
    session_factory: sessionmaker[Session],
) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an ASGI client using the isolated test database."""

    def override_get_db() -> Iterator[Session]:
        """Yield a test database session for a request."""
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Work that outlives the request, such as persisting a streamed answer, must
    # land in the same isolated database instead of the module-level factory.
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    # Rate limiters keep process-wide state, so every test gets fresh instances;
    # tests that exercise limiting override these with a tighter limiter.
    settings = get_settings()
    login_limiter = FixedWindowRateLimiter(
        settings.login_max_attempts,
        settings.login_window_seconds,
    )
    chat_limiter = FixedWindowRateLimiter(
        settings.chat_max_requests,
        settings.chat_window_seconds,
    )
    app.dependency_overrides[get_login_rate_limiter] = lambda: login_limiter
    app.dependency_overrides[get_chat_rate_limiter] = lambda: chat_limiter
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
