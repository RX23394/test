"""Tests for the uniform error response contract."""

import logging
from collections.abc import Iterator

import httpx
import pytest

from app.core.exceptions import INTERNAL_ERROR_MESSAGE
from app.main import create_app


class RecordingHandler(logging.Handler):
    """Collect log records independently of the global logging configuration."""

    def __init__(self) -> None:
        """Initialise the handler with an empty record list."""
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store the emitted record."""
        self.records.append(record)


@pytest.fixture
def handler_for_exception_logger() -> Iterator[RecordingHandler]:
    """Attach a recording handler to the module logger under test."""
    handler = RecordingHandler()
    logger = logging.getLogger("app.core.exceptions")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(previous_level)


@pytest.mark.asyncio
async def test_unhandled_exception_returns_uniform_error_response(
    handler_for_exception_logger: RecordingHandler,
) -> None:
    """Unexpected errors become a uniform 500 instead of a raw traceback."""
    application = create_app()

    @application.get("/boom")
    async def boom() -> None:
        """Raise an unexpected error for the handler under test."""
        raise RuntimeError("secret internal detail")

    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "status": "error",
        "message": INTERNAL_ERROR_MESSAGE,
    }
    assert "secret internal detail" not in response.text

    records = handler_for_exception_logger.records
    assert len(records) == 1
    assert records[0].getMessage() == "Unhandled error while processing GET /boom"
    assert isinstance(records[0].exc_info[1], RuntimeError)
