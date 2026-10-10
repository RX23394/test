"""Document indexing response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class DocumentIndexResult(BaseModel):
    """Summary of a completed document indexing operation."""

    document_id: int
    chunk_count: int = Field(ge=0)


class DocumentIndexJobResponse(BaseModel):
    """Handle returned by the background indexing endpoint.

    Parsing, embedding, and writing a large document can take minutes, so the
    request only claims the job and returns its identifier; the document row
    carries the progress (``processing`` → ``indexed``/``failed``).
    """

    document_id: int
    job_id: str
    status: Literal["processing"] = "processing"
