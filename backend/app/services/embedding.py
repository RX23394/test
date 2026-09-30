"""Process-cached CPU embedding generation with multilingual E5."""

from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_DEVICE = "cpu"
EMBEDDING_DIMENSION = 384
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
DEFAULT_BATCH_SIZE = 32


class SentenceEncoder(Protocol):
    """Subset of the sentence-transformers encoder used by the service."""

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

    def get_sentence_embedding_dimension(self) -> int:
        """Return the fixed output dimension of the configured E5 model."""
        return EMBEDDING_DIMENSION

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document texts after adding the E5 passage prefix."""
        if not texts:
            return []
        prefixed = [f"{PASSAGE_PREFIX}{text}" for text in texts]
        return self._encode(prefixed)

    def embed_query(self, text: str) -> list[list[float]]:
        """Embed one query as a single-row list after adding its E5 prefix."""
        return self._encode([f"{QUERY_PREFIX}{text}"])

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
