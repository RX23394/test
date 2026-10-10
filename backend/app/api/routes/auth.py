"""Authentication API endpoints."""

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.cookies import clear_auth_cookie, set_auth_cookie
from app.auth.dependencies import CurrentUser, SessionDependency
from app.auth.security import create_access_token
from app.core.rate_limit import (
    FixedWindowRateLimiter,
    client_key,
    get_login_rate_limiter,
)
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, UserResponse
from app.schemas.response import ResponseModel
from app.services.auth import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOGIN_RATE_LIMIT_MESSAGE = "Too many login attempts, try again later"
LoginRateLimiterDependency = Annotated[
    FixedWindowRateLimiter,
    Depends(get_login_rate_limiter),
]


def _retry_after_seconds(limiter: FixedWindowRateLimiter, key: str) -> int:
    """Return a whole-second Retry-After value for a limited request."""
    return max(1, math.ceil(limiter.retry_after(key)))


@router.post(
    "/login",
    response_model=ResponseModel[UserResponse],
    response_model_exclude_none=True,
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    login_limiter: LoginRateLimiterDependency,
) -> ResponseModel[UserResponse]:
    """Authenticate a user and set an HttpOnly access-token cookie."""
    key = client_key(request, payload.username)
    if not login_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=LOGIN_RATE_LIMIT_MESSAGE,
            headers={"Retry-After": str(_retry_after_seconds(login_limiter, key))},
        )

    user = AuthService(UserRepository(session)).authenticate(
        payload.username,
        payload.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    login_limiter.reset(key)
    set_auth_cookie(response, create_access_token(user.id))
    return ResponseModel(status="ok", data=UserResponse.model_validate(user))


@router.post(
    "/logout",
    response_model=ResponseModel[None],
    response_model_exclude_none=True,
)
async def logout(response: Response) -> ResponseModel[None]:
    """Clear the authentication cookie."""
    clear_auth_cookie(response)
    return ResponseModel(status="ok")


@router.get(
    "/me",
    response_model=ResponseModel[UserResponse],
    response_model_exclude_none=True,
)
async def get_me(current_user: CurrentUser) -> ResponseModel[UserResponse]:
    """Return the currently authenticated user."""
    return ResponseModel(
        status="ok",
        data=UserResponse.model_validate(current_user),
    )
