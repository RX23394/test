"""Conversation API request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """Optional title used when creating a conversation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, max_length=255)


class ConversationUpdate(BaseModel):
    """Validated conversation title update."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    """Public conversation summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """Persisted chat message returned to its owner."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    """Conversation summary with ordered messages."""

    conversation: ConversationResponse
    messages: list[MessageResponse]
