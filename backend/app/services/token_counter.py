"""Token counting with an optional tiktoken dependency."""

from typing import Protocol

DEFAULT_ENCODING_NAME = "cl100k_base"


class _Encoding(Protocol):
    """Minimal encoding contract required by TokenCounter."""

    def encode(self, text: str) -> list[int]:
        """Encode text into token identifiers."""
        ...


def _load_tiktoken_encoding(encoding_name: str) -> _Encoding | None:
    """Load a tiktoken encoding or return None when it is unavailable."""
    try:
        import tiktoken
    except ImportError:
        return None
    return tiktoken.get_encoding(encoding_name)


class TokenCounter:
    """Count tokens with tiktoken and fall back to character length."""

    def __init__(self, encoding_name: str = DEFAULT_ENCODING_NAME) -> None:
        """Initialize the preferred tokenizer when it is installed."""
        self._encoding = _load_tiktoken_encoding(encoding_name)

    def count(self, text: str) -> int:
        """Return a tokenizer count or a character-length estimate."""
        if self._encoding is None:
            return len(text)
        return len(self._encoding.encode(text))
