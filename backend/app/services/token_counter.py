"""Token counting with optional tiktoken and embedding-tokenizer backends."""

from collections.abc import Mapping
from functools import lru_cache
from typing import Protocol

DEFAULT_ENCODING_NAME = "cl100k_base"
# Chunk sizing has to be measured with the tokenizer that the embedding model
# actually applies, because cl100k and the E5 tokenizer disagree sharply on
# ASCII-dense text: a rule of "+-+-+-+-+-+" costs one cl100k token but up to five
# E5 tokens. Sized with cl100k, such a chunk fits the 400-token budget yet is
# rejected by the encoder's 512-token window.
EMBEDDING_ENCODING_NAME = "embedding"
# Fixed per-passage overhead the encoder adds on top of the chunk text. The
# begin/end-of-sequence pair is counted here as a constant because ChunkService
# counts one word at a time and the tokenizer would otherwise add a pair to
# every word.
EMBEDDING_PASSAGE_OVERHEAD = 2


class _Encoding(Protocol):
    """Minimal encoding contract required by TokenCounter."""

    def encode(self, text: str) -> list[int]:
        """Encode text into token identifiers."""
        ...


class _EmbeddingEncoding:
    """Measure text with the embedding model's own tokenizer.

    Special tokens are excluded: ``ChunkService`` counts one word at a time, so
    including them would add a begin/end-of-sequence pair to every word and
    shrink the window by roughly twice the word count. ``EMBEDDING_PASSAGE_OVERHEAD``
    accounts for the single pair the encoder adds to a complete passage, and
    ``ChunkService`` adds the ``passage: `` prefix once for the same reason.
    """

    def __init__(self, tokenizer: object) -> None:
        """Wrap the model tokenizer."""
        self._tokenizer = tokenizer

    def encode(self, text: str) -> list[int]:
        """Return the encoder token ids for one text fragment."""
        encoded = self._tokenizer(  # type: ignore[operator]
            text,
            add_special_tokens=False,
        )
        input_ids = encoded["input_ids"] if isinstance(encoded, Mapping) else encoded
        return list(input_ids)


@lru_cache(maxsize=1)
def _load_embedding_encoding() -> _Encoding | None:
    """Load the embedding model's tokenizer, or None when it is unavailable."""
    try:
        from sentence_transformers import SentenceTransformer

        from app.services.embedding import MODEL_DEVICE, MODEL_NAME

        tokenizer = SentenceTransformer(MODEL_NAME, device=MODEL_DEVICE).tokenizer
    except Exception:  # pragma: no cover - depends on optional model assets
        return None
    return _EmbeddingEncoding(tokenizer)


def embedding_prefix_tokens() -> int:
    """Return how many tokens the encoder's passage prefix costs."""
    encoding = _load_embedding_encoding()
    if encoding is None:  # pragma: no cover - mirrors the counter fallback
        return 0
    try:
        from app.services.embedding import PASSAGE_PREFIX

        return len(encoding.encode(PASSAGE_PREFIX))
    except Exception:  # pragma: no cover - defensive
        return 0


def _load_tiktoken_encoding(encoding_name: str) -> _Encoding | None:
    """Load a tiktoken encoding or return None when it is unavailable."""
    try:
        import tiktoken
    except ImportError:
        return None
    return tiktoken.get_encoding(encoding_name)


class TokenCounter:
    """Count tokens with a real tokenizer and fall back to character length."""

    def __init__(self, encoding_name: str = DEFAULT_ENCODING_NAME) -> None:
        """Initialize the preferred tokenizer when it is installed."""
        if encoding_name == EMBEDDING_ENCODING_NAME:
            self._encoding: _Encoding | None = _load_embedding_encoding()
        else:
            self._encoding = _load_tiktoken_encoding(encoding_name)

    def count(self, text: str) -> int:
        """Return a tokenizer count or a character-length estimate."""
        if self._encoding is None:
            return len(text)
        encoded = self._encoding.encode(text)
        return len(encoded)
