"""Document chunk schemas."""

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A token-bounded document fragment with source metadata."""

    content: str
    page: int | None = None
    section: str | None = None
    chunk_index: int = Field(ge=0)
