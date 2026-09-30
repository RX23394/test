"""Shared API response schema."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResponseModel[DataT](BaseModel):
    """Uniform response envelope for API endpoints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    data: DataT | None = None
    message: str | None = None
