"""Document indexing response schemas."""

from pydantic import BaseModel, Field


class DocumentIndexResult(BaseModel):
    """Summary of a completed document indexing operation."""

    document_id: int
    chunk_count: int = Field(ge=0)
