"""Document database model."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class DocumentStatus(StrEnum):
    """Supported document processing states."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    """Uploaded document and its processing metadata."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    uploader_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            native_enum=False,
            values_callable=lambda status_type: [
                status.value for status in status_type
            ],
            validate_strings=True,
            create_constraint=True,
        ),
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
        nullable=False,
    )
    indexing_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    uploader: Mapped["User"] = relationship(back_populates="documents")
