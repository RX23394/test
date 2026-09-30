"""FastAPI authentication dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.security import AuthTokenError, decode_access_token
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository

SessionDependency = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, session: SessionDependency) -> User:
    """Return the active user represented by the authentication cookie."""
    token = request.cookies.get(get_settings().auth_cookie_name)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = decode_access_token(token)
        user_id = int(payload.sub)
    except (AuthTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    user = UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_admin(current_user: CurrentUser) -> User:
    """Return the current user when they have administrator privileges."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
