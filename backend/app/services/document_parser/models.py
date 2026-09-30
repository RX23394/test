"""Data structures returned by document parsers."""

from pydantic import BaseModel, ConfigDict


class DocumentPage(BaseModel):
    """Text extracted from one numbered document page."""

    model_config = ConfigDict(extra="forbid")

    page_number: int
    text: str


class DocumentContent(BaseModel):
    """Page-preserving text extracted from a document."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    pages: list[DocumentPage]
