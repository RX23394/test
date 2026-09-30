"""Database-independent document chunk model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """Represent one text chunk and its source metadata."""

    id: str
    document_id: int | None
    page: int | None
    section: str | None
    chunk_index: int
    text: str
    token_count: int

    @property
    def content(self) -> str:
        """Return text through the legacy indexing attribute name."""
        return self.text
