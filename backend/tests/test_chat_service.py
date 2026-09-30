"""Tests for OpenAI-compatible citation-grounded streaming."""

import json
from collections.abc import Iterator, Sequence
from typing import cast

import httpx
from openai import OpenAI

from app.api.routes.chat import stream_chat_events
from app.core.config import Settings
from app.schemas.chat import CitationSource
from app.services.llm_provider import LLMProvider
from app.services.prompt_builder import PromptBuilder


class FailingLLMProvider:
    """Raise during streaming to exercise the SSE error envelope."""

    def stream_chat(
        self,
        messages: Sequence[object],
    ) -> Iterator[str]:
        """Raise a provider failure before producing a text delta."""
        del messages
        raise RuntimeError("provider unavailable")


def test_chat_service_streams_deltas_with_numbered_sources() -> None:
    """The compatible request includes numbered sources and yields text deltas."""
    requests: list[dict[str, object]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        """Capture the request and return an OpenAI-compatible SSE stream."""
        requests.append(json.loads(request.content))
        body = "\n\n".join(
            [
                'data: {"id":"chatcmpl-1","object":"chat.completion.chunk",'
                '"created":1,"model":"test-model","choices":[{"index":0,'
                '"delta":{"content":"Routing "},"finish_reason":null}]}',
                'data: {"id":"chatcmpl-1","object":"chat.completion.chunk",'
                '"created":1,"model":"test-model","choices":[{"index":0,'
                '"delta":{"content":"uses OSPF [S1]."},"finish_reason":null}]}',
                "data: [DONE]",
                "",
            ]
        )
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handle_request))
    client = OpenAI(
        api_key="test-key",
        base_url="http://compatible.test/v1",
        http_client=http_client,
    )
    provider = LLMProvider(
        client,
        Settings(
            openai_api_key="test-key",
            openai_base_url="http://compatible.test/v1",
            openai_model="test-model",
        ),
    )
    sources = [
        CitationSource(
            label="S1",
            document_id=1,
            chunk_index=0,
            content="OSPF is a link-state routing protocol.",
            page=3,
            section="Routing",
        ),
        CitationSource(
            label="S2",
            document_id=1,
            chunk_index=1,
            content="Ethernet is used on local networks.",
        ),
    ]

    messages = PromptBuilder().build_from_sources("What is OSPF?", sources)
    deltas = list(provider.stream_chat(messages))

    assert deltas == ["Routing ", "uses OSPF [S1]."]
    assert len(requests) == 1
    request = requests[0]
    assert request["model"] == "test-model"
    assert request["stream"] is True
    messages = request["messages"]
    assert isinstance(messages, list)
    assert "[S1]" in str(messages)
    assert "[S2]" in str(messages)
    assert "page: 3" in str(messages)
    assert "section: Routing" in str(messages)
    http_client.close()


def test_chat_stream_emits_uniform_error_event() -> None:
    """Provider failures become a terminal uniform SSE error event."""
    provider = cast(LLMProvider, FailingLLMProvider())

    source = CitationSource(
        label="S1",
        document_id=1,
        chunk_index=0,
        content="source",
    )
    events = list(stream_chat_events("question", [source], [], provider))

    assert '"status":"error"' in events[0]
    assert '"message":"LLM API request failed"' in events[0]
    assert all('"type":"done"' not in event for event in events)
