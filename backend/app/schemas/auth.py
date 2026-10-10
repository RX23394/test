"""Authentication request and response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class LoginRequest(BaseModel):
    """Credentials accepted by the login endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class UserCreate(BaseModel):
    """Validated data used to create a user."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)


class ManagedUserCreate(UserCreate):
    """Validated account data accepted by administrators."""

    role: Literal["admin", "user"] = "user"


class UserStatusUpdate(BaseModel):
    """Validated account activation state update."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool


class UserRoleUpdate(BaseModel):
    """Validated account role update."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["admin", "user"]


class UserResponse(BaseModel):
    """Public user data returned by authentication endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class ManagedUserResponse(UserResponse):
    """User data exposed by administrator management endpoints."""

    @computed_field
    @property
    def role(self) -> Literal["admin", "user"]:
        """Return the user role derived from administrator privileges."""
        return "admin" if self.is_admin else "user"


class TokenPayload(BaseModel):
    """Validated claims stored in an access token."""

    sub: str
    exp: datetime
    iat: datetime
    type: Literal["access"]
    # Tokens issued before revocation support carry no version; they belong to
    # the first generation, which is what existing users start at.
    ver: int = 1
