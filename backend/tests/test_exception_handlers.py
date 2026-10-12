"""Tests for the uniform error response contract."""

import logging
from collections.abc import Iterator

import httpx
import pytest

from app.core.config import get_settings
from app.core.exceptions import INTERNAL_ERROR_MESSAGE
from app.main import create_app
from app.rag.dependencies import EMBEDDING_UNAVAILABLE_MESSAGE
from app.services.embedding import EmbeddingServiceUnavailableError


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


async def _unhandled_error_response(origin: str) -> httpx.Response:
    """Request a route that always raises, from the given browser origin."""
    application = create_app()

    @application.get("/boom")
    async def boom() -> None:
        """Raise an unexpected error for the handler under test."""
        raise RuntimeError("secret internal detail")

    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Origin": origin},
    ) as client:
        return await client.get("/boom")


@pytest.mark.asyncio
async def test_unhandled_error_carries_cors_headers() -> None:
    """A cross-origin client can read the uniform 500 instead of a CORS failure.

    ``ServerErrorMiddleware`` sends this response on the raw ASGI ``send``, so
    without the headers added here the browser withholds the body and the only
    thing the frontend can report is "Failed to fetch" -- which hides the real
    error and was the reason a 500 surfaced as a network failure.
    """
    settings = get_settings()

    response = await _unhandled_error_response(settings.frontend_origin)

    assert response.status_code == 500
    assert response.json()["message"] == INTERNAL_ERROR_MESSAGE
    assert response.headers["access-control-allow-origin"] == settings.frontend_origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "origin" in response.headers["vary"].lower()


@pytest.mark.asyncio
async def test_unhandled_error_omits_cors_headers_for_unknown_origin() -> None:
    """An origin outside the allow-list gains nothing from the error path."""
    response = await _unhandled_error_response("http://evil.example.com")

    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_unavailable_encoder_reports_503_with_cors_headers() -> None:
    """A missing encoder is an unavailable service, not a server fault.

    The encoder is resolved before any route body runs, so this handler is the
    only place that can turn the failure into an actionable status code.
    """
    application = create_app()

    @application.get("/needs-model")
    async def needs_model() -> None:
        """Fail the way a missing embedding model does."""
        raise EmbeddingServiceUnavailableError("no model")

    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Origin": get_settings().frontend_origin},
    ) as client:
        response = await client.get("/needs-model")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "message": EMBEDDING_UNAVAILABLE_MESSAGE,
    }
    assert "access-control-allow-origin" in response.headers
