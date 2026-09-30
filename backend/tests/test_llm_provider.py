"""Tests for the prompt-agnostic OpenAI-compatible LLM provider."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIError, APITimeoutError, BadRequestError, OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.core.config import Settings
from app.services.llm_errors import (
    LLMAPIError,
    LLMTimeoutError,
    LLMTokenLimitError,
)
from app.services.llm_provider import LLMProvider, LLMProviderResponseError


def create_messages() -> list[ChatCompletionMessageParam]:
    """Return caller-owned messages without a provider-generated prompt."""
    return cast(
        list[ChatCompletionMessageParam],
        [
            {"role": "system", "content": "Caller system instruction"},
            {"role": "user", "content": "What is OSPF?"},
        ],
    )


def create_settings() -> Settings:
    """Return deterministic OpenAI-compatible provider settings."""
    return Settings(
        openai_base_url="http://compatible.test/v1",
        openai_api_key="test-key",
        openai_model="compatible-model",
    )


def test_settings_load_llm_values_from_dotenv(tmp_path: Path) -> None:
    """LLM base URL, API key, and model are loaded from a dotenv file."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_BASE_URL=http://dotenv.test/v1\n"
        "OPENAI_API_KEY=dotenv-key\n"
        "OPENAI_MODEL=dotenv-model\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_path)

    assert settings.openai_base_url == "http://dotenv.test/v1"
    assert settings.openai_api_key == "dotenv-key"
    assert settings.openai_model == "dotenv-model"


def test_provider_builds_official_sdk_client_from_settings() -> None:
    """The default client uses compatible base URL and API key settings."""
    settings = create_settings()

    with patch("app.services.llm_provider.OpenAI") as openai_class:
        LLMProvider(settings=settings)

    openai_class.assert_called_once_with(
        api_key="test-key",
        base_url="http://compatible.test/v1",
        timeout=60.0,
    )


def test_chat_returns_content_and_preserves_messages() -> None:
    """Non-streaming chat passes exact messages and returns response text."""
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OSPF is a routing protocol.")
            )
        ]
    )
    messages = create_messages()
    original_messages = [dict(message) for message in messages]
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    result = provider.chat(messages)

    assert result == "OSPF is a routing protocol."
    assert messages == original_messages
    client.chat.completions.create.assert_called_once_with(
        model="compatible-model",
        messages=messages,
        stream=False,
    )


def test_stream_chat_yields_non_empty_sdk_deltas() -> None:
    """Streaming chat yields text deltas and skips empty SDK events."""
    client = MagicMock()
    stream_context = MagicMock()
    stream_context.__enter__.return_value = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="OSPF "))]
        ),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        SimpleNamespace(choices=[]),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="details"))]
        ),
    ]
    client.chat.completions.create.return_value = stream_context
    messages = create_messages()
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    deltas = list(provider.stream_chat(messages))

    assert deltas == ["OSPF ", "details"]
    client.chat.completions.create.assert_called_once_with(
        model="compatible-model",
        messages=messages,
        stream=True,
    )
    stream_context.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        ),
    ],
)
def test_chat_rejects_responses_without_text(response: object) -> None:
    """Malformed compatible responses raise the public provider error."""
    client = MagicMock()
    client.chat.completions.create.return_value = response
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    with pytest.raises(LLMProviderResponseError):
        provider.chat(create_messages())


def test_provider_normalizes_timeout_error() -> None:
    """SDK timeouts become stable application timeout errors."""
    client = MagicMock()
    request = httpx.Request("POST", "https://provider.test/v1/chat")
    client.chat.completions.create.side_effect = APITimeoutError(request=request)
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    with pytest.raises(LLMTimeoutError, match="LLM request timed out"):
        provider.chat(create_messages())


def test_provider_normalizes_api_error() -> None:
    """SDK API failures become stable application API errors."""
    client = MagicMock()
    request = httpx.Request("POST", "https://provider.test/v1/chat")
    client.chat.completions.create.side_effect = APIError(
        "private provider detail",
        request=request,
        body=None,
    )
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    with pytest.raises(LLMAPIError, match="LLM API request failed"):
        provider.chat(create_messages())


def test_provider_normalizes_token_limit_error() -> None:
    """Context-length rejections become stable token-limit errors."""
    client = MagicMock()
    request = httpx.Request("POST", "https://provider.test/v1/chat")
    response = httpx.Response(400, request=request)
    client.chat.completions.create.side_effect = BadRequestError(
        "maximum context length exceeded",
        response=response,
        body={"code": "context_length_exceeded"},
    )
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    with pytest.raises(LLMTokenLimitError, match="Token limit exceeded"):
        provider.chat(create_messages())


def test_stream_provider_normalizes_sdk_error() -> None:
    """Streaming setup failures use the same normalized error contract."""
    client = MagicMock()
    request = httpx.Request("POST", "https://provider.test/v1/chat")
    client.chat.completions.create.side_effect = APITimeoutError(request=request)
    provider = LLMProvider(cast(OpenAI, client), create_settings())

    with pytest.raises(LLMTimeoutError, match="LLM request timed out"):
        list(provider.stream_chat(create_messages()))
