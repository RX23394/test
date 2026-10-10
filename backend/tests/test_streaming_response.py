"""Tests for named server-sent chat streaming events."""

from collections.abc import Iterator, Sequence
from typing import cast

import pytest
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.routes.chat import (
    CHAT_PERSISTENCE_ERROR_MESSAGE,
    create_streaming_response,
    stream_chat_events,
)
from app.schemas.chat import ChatRequest, CitationSource
from app.services.citation_resolver import Citation
from app.services.llm_errors import (
    LLMAPIError,
    LLMTimeoutError,
    LLMTokenLimitError,
)
from app.services.llm_provider import LLMProvider
from app.services.prompt_builder import INSUFFICIENT_KNOWLEDGE_RESPONSE


class TokenChatService:
    """Yield deterministic provider tokens without buffering an answer."""

    def __init__(self) -> None:
        """Initialize observable streaming state."""
        self.started = False

    def stream_chat(
        self,
        messages: Sequence[object],
    ) -> Iterator[str]:
        """Yield two separate text tokens."""
        del messages
        self.started = True
        yield "OSPF "
        yield "uses areas."


class FailingAfterTokenChatService:
    """Yield one token before simulating a provider stream failure."""

    def stream_chat(
        self,
        messages: Sequence[object],
    ) -> Iterator[str]:
        """Yield partial output and then raise an error."""
        del messages
        yield "partial"
        raise RuntimeError("stream interrupted")


def create_source() -> CitationSource:
    """Create one stable citation source for SSE tests."""
    return CitationSource(
        label="S1",
        document_id=1,
        chunk_index=0,
        content="OSPF is a link-state routing protocol.",
        page=12,
        section="Area",
    )


class ConfiguredFailingChatService:
    """Raise a configured normalized LLM failure during streaming."""

    def __init__(self, error: Exception) -> None:
        """Store the failure emitted by the fake provider."""
        self._error = error

    def stream_chat(
        self,
        messages: Sequence[object],
    ) -> Iterator[str]:
        """Raise the configured error without yielding a token."""
        del messages
        if False:
            yield ""
        raise self._error


def create_citation() -> Citation:
    """Create one database-resolved user-visible citation."""
    return Citation(
        id="S1",
        document="Cisco OSPF.pdf",
        page=12,
        section="Area",
        content="OSPF is a link-state routing protocol.",
    )


def test_stream_emits_named_citation_token_and_done_events() -> None:
    """Successful streams expose citations, each token, and completion."""
    service = cast(LLMProvider, TokenChatService())

    events = list(
        stream_chat_events(
            "What is OSPF?",
            [create_source()],
            [create_citation()],
            service,
        )
    )

    assert [event.splitlines()[0] for event in events] == [
        "event: token",
        "event: token",
        "event: citation",
        "event: done",
    ]
    assert '"data":"OSPF "' in events[0]
    assert '"data":"uses areas."' in events[1]
    assert "uses areas." not in events[0]
    assert '"id":"S1"' in events[2]
    assert '"document":"Cisco OSPF.pdf"' in events[2]
    assert '"page":12' in events[2]
    assert '"section":"Area"' in events[2]
    assert '"content":"OSPF is a link-state routing protocol."' in events[2]


def test_search_empty_returns_fallback_without_calling_model() -> None:
    """No sources produce the fixed answer, empty citations, and completion."""
    token_service = TokenChatService()
    service = cast(LLMProvider, token_service)

    events = list(stream_chat_events("question", [], [], service))

    assert token_service.started is False
    assert [event.splitlines()[0] for event in events] == [
        "event: token",
        "event: citation",
        "event: done",
    ]
    assert INSUFFICIENT_KNOWLEDGE_RESPONSE in events[0]
    assert '"data":[]' in events[1]


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (LLMTimeoutError("provider detail"), "LLM request timed out"),
        (LLMAPIError("provider detail"), "LLM API request failed"),
        (LLMTokenLimitError("provider detail"), "Token limit exceeded"),
    ],
)
def test_stream_returns_normalized_llm_error(
    error: Exception,
    expected_message: str,
) -> None:
    """Known provider failures use stable uniform SSE error responses."""
    failing_service = ConfiguredFailingChatService(error)
    service = cast(LLMProvider, failing_service)

    events = list(
        stream_chat_events(
            "question",
            [create_source()],
            [create_citation()],
            service,
        )
    )

    assert len(events) == 1
    assert events[0].startswith("event: error\n")
    assert '"status":"error"' in events[0]
    assert f'"message":"{expected_message}"' in events[0]


def test_stream_is_lazy_and_does_not_build_the_full_answer_first() -> None:
    """The iterator starts provider generation only when a token is requested."""
    token_service = TokenChatService()
    service = cast(LLMProvider, token_service)
    events = stream_chat_events(
        "question", [create_source()], [create_citation()], service
    )
    first_token_event = next(events)

    assert token_service.started is True
    assert first_token_event.startswith("event: token\n")
    assert '"data":"OSPF "' in first_token_event
    assert "uses areas." not in first_token_event
    assert '"data":"uses areas."' in next(events)


def test_stream_converts_provider_failure_to_terminal_error_event() -> None:
    """A stream failure emits error instead of a misleading done event."""
    service = cast(LLMProvider, FailingAfterTokenChatService())

    events = list(
        stream_chat_events("question", [create_source()], [create_citation()], service)
    )

    assert [event.splitlines()[0] for event in events] == [
        "event: token",
        "event: error",
    ]
    assert '"status":"error"' in events[-1]
    assert '"message":"LLM API request failed"' in events[-1]
    assert all(not event.startswith("event: done\n") for event in events)


def test_stream_converts_persistence_failure_to_terminal_error_event() -> None:
    """A completed answer that cannot be saved ends with a stable error."""
    service = cast(LLMProvider, TokenChatService())

    def fail_persistence(answer: str) -> None:
        """Simulate a database failure after provider streaming completes."""
        assert answer == "OSPF uses areas."
        raise RuntimeError("database unavailable")

    events = list(
        stream_chat_events(
            "question",
            [create_source()],
            [create_citation()],
            service,
            fail_persistence,
        )
    )

    assert [event.splitlines()[0] for event in events] == [
        "event: token",
        "event: token",
        "event: error",
    ]
    assert CHAT_PERSISTENCE_ERROR_MESSAGE in events[-1]
    assert all(not event.startswith("event: citation\n") for event in events)
    assert all(not event.startswith("event: done\n") for event in events)


def test_fastapi_streaming_response_uses_sse_and_disables_buffering() -> None:
    """The response wrapper configures event-stream transport headers."""
    response = create_streaming_response(iter(["event: done\ndata: {}\n\n"]))

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_chat_stream_request_accepts_conversation_and_message() -> None:
    """The endpoint contract validates and normalizes both required fields."""
    payload = ChatRequest(
        conversation_id=1,
        message="  What is OSPF?  ",
    )

    assert payload.conversation_id == 1
    assert payload.message == "What is OSPF?"


@pytest.mark.parametrize(
    "payload",
    [
        {"conversation_id": 0, "message": "question"},
        {"conversation_id": 1, "message": "   "},
        {"query": "legacy field"},
    ],
)
def test_chat_stream_request_rejects_invalid_contract(
    payload: dict[str, object],
) -> None:
    """Invalid IDs, empty messages, and the legacy query field are rejected."""
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)
