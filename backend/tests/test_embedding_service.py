"""Tests for multilingual E5 embedding generation."""

import sys
from types import ModuleType

import numpy as np
import pytest
from numpy.typing import NDArray

from app.services import embedding as embedding_module
from app.services.embedding import (
    EMBEDDING_DIMENSION,
    MAX_SEQUENCE_LENGTH,
    MODEL_DEVICE,
    MODEL_NAME,
    EmbeddingDimensionError,
    EmbeddingInputTooLongError,
    EmbeddingService,
)


class FakeSentenceEncoder:
    """Record encoder calls and return fixed-size vectors."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        """Initialize recorded call state and output dimension."""
        self.dimension = dimension
        self.sentences: list[str] = []
        self.batch_size: int | None = None
        self.show_progress_bar: bool | None = None
        self.convert_to_numpy: bool | None = None
        self.normalize_embeddings: bool | None = None

    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> NDArray[np.float32]:
        """Record E5 input and return deterministic vectors."""
        self.sentences = sentences
        self.batch_size = batch_size
        self.show_progress_bar = show_progress_bar
        self.convert_to_numpy = convert_to_numpy
        self.normalize_embeddings = normalize_embeddings
        return np.ones((len(sentences), self.dimension), dtype=np.float32)


def test_embedding_service_uses_passage_prefix() -> None:
    """Document content is embedded with the required passage prefix."""
    encoder = FakeSentenceEncoder()

    vectors = EmbeddingService(encoder).embed_passages(["first", "second"])

    assert encoder.sentences == ["passage: first", "passage: second"]
    assert encoder.normalize_embeddings is True
    assert encoder.show_progress_bar is False
    assert encoder.convert_to_numpy is True
    assert len(vectors) == 2
    assert len(vectors[0]) == EMBEDDING_DIMENSION
    assert isinstance(vectors[0][0], float)


def test_embedding_service_uses_query_prefix_and_two_dimensional_result() -> None:
    """A query receives its prefix and returns one vector in a row list."""
    encoder = FakeSentenceEncoder()

    vectors = EmbeddingService(encoder).embed_query("network routing")

    assert encoder.sentences == ["query: network routing"]
    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIMENSION


def test_embedding_service_skips_empty_passage_batches() -> None:
    """An empty passage collection does not invoke the model."""
    encoder = FakeSentenceEncoder()

    vectors = EmbeddingService(encoder).embed_passages([])

    assert vectors == []
    assert encoder.sentences == []


def test_embedding_service_rejects_wrong_vector_dimension() -> None:
    """Unexpected model dimensions are rejected before returning vectors."""
    encoder = FakeSentenceEncoder(dimension=3)

    with pytest.raises(EmbeddingDimensionError):
        EmbeddingService(encoder).embed_query("routing")


class FakeTokenizer:
    """Report a fixed number of tokens for every text."""

    def __init__(self, token_length: int) -> None:
        """Store the reported token length."""
        self.token_length = token_length

    def __call__(self, text: str) -> dict[str, list[int]]:
        """Return a token-id list of the configured length."""
        del text
        return {"input_ids": list(range(self.token_length))}


class TokenizerSentenceEncoder(FakeSentenceEncoder):
    """Encoder double that also exposes a tokenizer."""

    def __init__(self, token_length: int) -> None:
        """Attach a tokenizer reporting ``token_length`` tokens."""
        super().__init__()
        self.tokenizer = FakeTokenizer(token_length)


def test_embedding_service_pins_the_encoder_sequence_limit() -> None:
    """The E5 truncation limit is set explicitly instead of left implicit."""
    encoder = FakeSentenceEncoder()

    EmbeddingService(encoder)

    assert encoder.max_seq_length == MAX_SEQUENCE_LENGTH


def test_embedding_service_rejects_a_passage_over_the_encoder_limit() -> None:
    """A passage that would be truncated is rejected before encoding."""
    encoder = TokenizerSentenceEncoder(MAX_SEQUENCE_LENGTH + 1)

    with pytest.raises(EmbeddingInputTooLongError, match="exceeds"):
        EmbeddingService(encoder).embed_passages(["long passage"])

    assert encoder.sentences == []


def test_embedding_service_accepts_a_passage_at_the_encoder_limit() -> None:
    """A passage exactly at the limit is still embedded."""
    encoder = TokenizerSentenceEncoder(MAX_SEQUENCE_LENGTH)

    vectors = EmbeddingService(encoder).embed_passages(["boundary passage"])

    assert len(vectors) == 1


def test_embedding_service_warns_but_embeds_an_over_long_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Queries only key the search, so they warn instead of failing."""
    encoder = TokenizerSentenceEncoder(MAX_SEQUENCE_LENGTH + 10)
    service = EmbeddingService(encoder)

    with caplog.at_level("WARNING", logger="app.services.embedding"):
        vectors = service.embed_query("very long question")

    assert len(vectors) == 1
    assert "exceeds" in caplog.text


def test_default_model_loads_once_on_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default services share one process-cached CPU model instance."""
    calls: list[tuple[str, str]] = []
    encoder = FakeSentenceEncoder()
    fake_module = ModuleType("sentence_transformers")

    def create_model(model_name: str, *, device: str) -> FakeSentenceEncoder:
        """Record model construction and return the fake encoder."""
        calls.append((model_name, device))
        return encoder

    fake_module.SentenceTransformer = create_model  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    embedding_module._get_default_model.cache_clear()
    try:
        first = EmbeddingService()
        second = EmbeddingService()

        first.embed_query("first")
        second.embed_passages(["second"])

        assert calls == [(MODEL_NAME, MODEL_DEVICE)]
    finally:
        embedding_module._get_default_model.cache_clear()
