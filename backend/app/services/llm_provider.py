"""Prompt-agnostic OpenAI-compatible LLM provider."""

from collections.abc import Iterator, Sequence

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.core.config import Settings, get_settings
from app.services.llm_errors import LLMAPIError, translate_openai_error


class LLMProviderResponseError(LLMAPIError):
    """Raised when a provider response does not contain a message choice."""


class LLMProvider:
    """Call OpenAI or an OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        client: OpenAI | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the SDK client and model from application settings."""
        resolved_settings = settings if settings is not None else get_settings()
        self._client = client or OpenAI(
            api_key=resolved_settings.openai_api_key,
            base_url=resolved_settings.openai_base_url,
            timeout=resolved_settings.openai_timeout_seconds,
        )
        self._model = resolved_settings.openai_model

    def chat(self, messages: Sequence[ChatCompletionMessageParam]) -> str:
        """Return one complete response without modifying caller messages."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=list(messages),
                stream=False,
            )
        except Exception as exc:
            translated_error = translate_openai_error(exc)
            if translated_error is None:
                raise
            raise translated_error from exc
        if not response.choices:
            raise LLMProviderResponseError("LLM response contained no choices")
        content = response.choices[0].message.content
        if content is None:
            raise LLMProviderResponseError("LLM response contained no text")
        return content

    def stream_chat(
        self,
        messages: Sequence[ChatCompletionMessageParam],
    ) -> Iterator[str]:
        """Yield non-empty text deltas without modifying caller messages."""
        try:
            with self._client.chat.completions.create(
                model=self._model,
                messages=list(messages),
                stream=True,
            ) as stream:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
        except Exception as exc:
            translated_error = translate_openai_error(exc)
            if translated_error is None:
                raise
            raise translated_error from exc
