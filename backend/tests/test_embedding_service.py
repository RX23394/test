"""Tests for multilingual E5 embedding generation."""

import os
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from numpy.typing import NDArray

from app.core.config import REPOSITORY_ROOT, Settings
from app.rag.dependencies import get_embedding_service
from app.services import embedding as embedding_module
from app.services.embedding import (
    EMBEDDING_DIMENSION,
    MAX_SEQUENCE_LENGTH,
    MODEL_DEVICE,
    MODEL_NAME,
    EmbeddingDimensionError,
    EmbeddingInputTooLongError,
    EmbeddingService,
    EmbeddingServiceUnavailableError,
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


def test_embedding_cache_prefers_the_configured_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An explicit EMBEDDING_CACHE_DIR wins over the project default."""
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "cache"))

    assert embedding_module.embedding_cache_directory() == tmp_path / "cache"


def test_embedding_cache_defaults_inside_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without configuration the cache stays project-local, not in %TEMP%.

    Torch derives its cache from ``tempfile.gettempdir()``, which raises when no
    candidate temporary directory is writable; that failure used to surface as an
    opaque 500 on the first question.
    """
    monkeypatch.delenv("EMBEDDING_CACHE_DIR", raising=False)

    expected = REPOSITORY_ROOT / embedding_module.DEFAULT_CACHE_DIRECTORY
    assert embedding_module.embedding_cache_directory() == expected
    assert expected.is_absolute()


def test_ensure_embedding_caches_creates_and_exports_the_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The torch caches are created and pointed at the resolved directory."""
    target = tmp_path / "cache"
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(target))
    for variable in embedding_module.CACHE_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    resolved = embedding_module.ensure_embedding_caches()

    assert resolved == target
    assert target.is_dir()
    for variable in embedding_module.CACHE_ENVIRONMENT_VARIABLES:
        assert os.environ[variable] == str(target)


def test_ensure_embedding_caches_keeps_operator_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An operator's own cache location is never overwritten."""
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "cache"))
    for variable in embedding_module.CACHE_ENVIRONMENT_VARIABLES:
        monkeypatch.setenv(variable, "D:/custom-cache")

    embedding_module.ensure_embedding_caches()

    for variable in embedding_module.CACHE_ENVIRONMENT_VARIABLES:
        assert os.environ[variable] == "D:/custom-cache"


def test_ensure_embedding_caches_survives_an_unwritable_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A cache that cannot be created is reported but never fatal.

    Torch emits its own error if it truly cannot write; replacing that with a
    failure from here would misattribute an optional optimization.
    """
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "cache"))
    for variable in embedding_module.CACHE_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    def refuse(*args: object, **kwargs: object) -> None:
        """Simulate a read-only or denied location."""
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "mkdir", refuse)

    resolved = embedding_module.ensure_embedding_caches()

    assert resolved == tmp_path / "cache"


def test_ensure_embedding_caches_enables_offline_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The cached encoder is used without contacting the Hub.

    ``huggingface_hub`` reads these once at import time, so a shell export made
    after the library is imported has no effect -- which is why the application
    sets them itself, before the encoder is imported.
    """
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "cache"))
    for variable in embedding_module.OFFLINE_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    embedding_module.ensure_embedding_caches()

    for variable in embedding_module.OFFLINE_ENVIRONMENT_VARIABLES:
        assert os.environ[variable] == "1"


def test_offline_mode_can_be_turned_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An operator who needs the Hub online is not forced offline."""
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        embedding_module,
        "get_settings",
        lambda: Settings(_env_file=None, embedding_offline=False),
    )
    for variable in embedding_module.OFFLINE_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    embedding_module.ensure_embedding_caches()

    for variable in embedding_module.OFFLINE_ENVIRONMENT_VARIABLES:
        assert variable not in os.environ


def test_unavailable_encoder_becomes_a_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that cannot be loaded is reported as unavailable, not as a 500.

    The chat route resolves this dependency before its own error handling, so
    the translation has to happen here for the client to receive a 503 with an
    actionable message.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        """Simulate a missing model and an unreachable model host."""
        raise OSError("no route to huggingface.co")

    monkeypatch.setattr(embedding_module, "_get_default_model", refuse)
    get_embedding_service.cache_clear()

    try:
        with pytest.raises(EmbeddingServiceUnavailableError) as failure:
            get_embedding_service()
    finally:
        get_embedding_service.cache_clear()

    assert "unavailable" in str(failure.value)
    assert isinstance(failure.value.__cause__, OSError)
