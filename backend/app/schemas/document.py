"""Document validation and serialization schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentCreate(BaseModel):
    """Validated metadata used to create a document."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    original_filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(ge=0)
    uploader_id: int = Field(gt=0)
    status: DocumentStatus = DocumentStatus.PENDING


class DocumentStatusUpdate(BaseModel):
    """Validated document processing status update."""

    model_config = ConfigDict(extra="forbid")

    status: DocumentStatus


class DocumentResponse(BaseModel):
    """Document metadata exposed to application consumers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    original_filename: str
    sha256: str
    file_size: int
    uploader_id: int
    status: DocumentStatus
    created_at: datetime
