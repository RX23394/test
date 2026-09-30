"""Pydantic schema package."""

from app.schemas.auth import LoginRequest, TokenPayload, UserCreate, UserResponse
from app.schemas.chat import ChatRequest, ChatStreamEvent, CitationSource
from app.schemas.chunk import Chunk
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentStatusUpdate,
)
from app.schemas.indexing import DocumentIndexResult
from app.schemas.response import ResponseModel
from app.schemas.search import (
    RetrievalCandidate,
    SearchApiResult,
    SearchRequest,
    SearchResult,
)

__all__ = [
    "ChatRequest",
    "ChatStreamEvent",
    "CitationSource",
    "Chunk",
    "DocumentCreate",
    "DocumentIndexResult",
    "DocumentResponse",
    "DocumentStatusUpdate",
    "LoginRequest",
    "ResponseModel",
    "RetrievalCandidate",
    "SearchApiResult",
    "SearchRequest",
    "SearchResult",
    "TokenPayload",
    "UserCreate",
    "UserResponse",
]
