"""Process-cached CPU embedding generation with multilingual E5."""

import logging
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_DEVICE = "cpu"
EMBEDDING_DIMENSION = 384
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
DEFAULT_BATCH_SIZE = 32
# E5 models are trained with a 512-token limit; anything longer is dropped by the
# tokenizer without any error. The limit is therefore pinned explicitly here and
# passages that would exceed it are rejected instead of silently truncated.
MAX_SEQUENCE_LENGTH = 512


class SentenceEncoder(Protocol):
    """Subset of the sentence-transformers encoder used by the service."""

    max_seq_length: int

    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> NDArray[np.float32]:
        """Encode sentences into a two-dimensional NumPy array."""
        ...


@lru_cache(maxsize=1)
def _get_default_model() -> SentenceEncoder:
    """Load the fixed CPU model once for the current application process."""
    from sentence_transformers import SentenceTransformer

    return cast(
        SentenceEncoder,
        SentenceTransformer(MODEL_NAME, device=MODEL_DEVICE),
    )


class EmbeddingDimensionError(RuntimeError):
    """Raised when the configured model returns an unexpected vector size."""


class EmbeddingInputTooLongError(RuntimeError):
    """Raised when a passage exceeds the encoder's maximum sequence length."""


class EmbeddingService:
    """Generate normalized passage and query vectors on the CPU."""

    def __init__(
        self,
        model: SentenceEncoder | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """Use an injected encoder or the process-cached E5 model."""
        self._model = model if model is not None else _get_default_model()
        self._batch_size = batch_size
        try:
            self._model.max_seq_length = MAX_SEQUENCE_LENGTH
        except (AttributeError, ValueError):  # pragma: no cover - unusual encoder
            logger.warning("Encoder does not expose a settable max_seq_length")

    def get_sentence_embedding_dimension(self) -> int:
        """Return the fixed output dimension of the configured E5 model."""
        return EMBEDDING_DIMENSION

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document texts after adding the E5 passage prefix.

        Passages are indexed content: a passage longer than the encoder limit
        would be stored with an incomplete vector, so it is rejected instead.
        """
        if not texts:
            return []
        prefixed = [f"{PASSAGE_PREFIX}{text}" for text in texts]
        lengths = self._token_lengths(prefixed)
        if lengths is not None and max(lengths) > MAX_SEQUENCE_LENGTH:
            raise EmbeddingInputTooLongError(
                f"Passage of {max(lengths)} tokens exceeds the "
                f"{MAX_SEQUENCE_LENGTH}-token encoder limit"
            )
        return self._encode(prefixed)

    def embed_query(self, text: str) -> list[list[float]]:
        """Embed one query as a single-row list after adding its E5 prefix."""
        prefixed = f"{QUERY_PREFIX}{text}"
        lengths = self._token_lengths([prefixed])
        if lengths is not None and lengths[0] > MAX_SEQUENCE_LENGTH:
            # A query only keys the search, so truncation changes ranking rather
            # than dropping indexed content; warn instead of failing the request.
            logger.warning(
                "Query of %s tokens exceeds the %s-token encoder limit",
                lengths[0],
                MAX_SEQUENCE_LENGTH,
            )
        return self._encode([prefixed])

    def _token_lengths(self, texts: list[str]) -> list[int] | None:
        """Return encoder token lengths, or None without a usable tokenizer."""
        tokenizer = getattr(self._model, "tokenizer", None)
        if tokenizer is None or not callable(tokenizer):
            return None
        lengths: list[int] = []
        for text in texts:
            encoded = tokenizer(text)
            token_ids = (
                encoded["input_ids"] if isinstance(encoded, Mapping) else encoded
            )
            lengths.append(len(token_ids))
        return lengths

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized vectors and validate their dimensions."""
        embeddings = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        vectors = embeddings.tolist()
        if any(len(vector) != EMBEDDING_DIMENSION for vector in vectors):
            raise EmbeddingDimensionError
        return [[float(value) for value in vector] for vector in vectors]
