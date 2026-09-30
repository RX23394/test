"""Tests for multilingual E5 embedding generation."""

import sys
from types import ModuleType

import numpy as np
import pytest
from numpy.typing import NDArray

from app.services import embedding as embedding_module
from app.services.embedding import (
    EMBEDDING_DIMENSION,
    MODEL_DEVICE,
    MODEL_NAME,
    EmbeddingDimensionError,
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
