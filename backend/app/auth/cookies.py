"""Authentication cookie helpers."""

from fastapi import Response

from app.core.config import get_settings


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the access token as a protected response cookie."""
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Remove the authentication cookie from the client."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
