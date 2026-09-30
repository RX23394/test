"""Stable application errors for OpenAI-compatible LLM failures."""

from openai import APIError, APITimeoutError, BadRequestError

LLM_TIMEOUT_MESSAGE = "LLM request timed out"
LLM_API_ERROR_MESSAGE = "LLM API request failed"
TOKEN_LIMIT_MESSAGE = "Token limit exceeded"
TOKEN_LIMIT_CODES = frozenset(
    {
        "context_length_exceeded",
        "max_tokens_exceeded",
        "token_limit_exceeded",
    }
)


class LLMServiceError(RuntimeError):
    """Base error safe for application service handling."""


class LLMTimeoutError(LLMServiceError):
    """Raised when an LLM request exceeds its provider timeout."""


class LLMAPIError(LLMServiceError):
    """Raised when an LLM provider rejects or fails a request."""


class LLMTokenLimitError(LLMServiceError):
    """Raised when an LLM request exceeds its context token limit."""


def translate_openai_error(error: Exception) -> LLMServiceError | None:
    """Translate known SDK errors without exposing provider details."""
    if isinstance(error, APITimeoutError):
        return LLMTimeoutError(LLM_TIMEOUT_MESSAGE)
    if isinstance(error, BadRequestError) and _is_token_limit_error(error):
        return LLMTokenLimitError(TOKEN_LIMIT_MESSAGE)
    if isinstance(error, APIError):
        return LLMAPIError(LLM_API_ERROR_MESSAGE)
    return None


def _is_token_limit_error(error: BadRequestError) -> bool:
    """Detect compatible-provider token-limit error variants."""
    if error.code in TOKEN_LIMIT_CODES:
        return True
    error_text = f"{error} {error.body}".lower()
    indicators = (
        "context length",
        "context_length",
        "maximum context",
        "max tokens",
        "token limit",
    )
    return any(indicator in error_text for indicator in indicators)
