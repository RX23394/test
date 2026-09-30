"""Authentication API endpoints."""

from fastapi import APIRouter, HTTPException, Response, status

from app.auth.cookies import clear_auth_cookie, set_auth_cookie
from app.auth.dependencies import CurrentUser, SessionDependency
from app.auth.security import create_access_token
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, UserResponse
from app.schemas.response import ResponseModel
from app.services.auth import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=ResponseModel[UserResponse],
    response_model_exclude_none=True,
)
async def login(
    payload: LoginRequest,
    response: Response,
    session: SessionDependency,
) -> ResponseModel[UserResponse]:
    """Authenticate a user and set an HttpOnly access-token cookie."""
    user = AuthService(UserRepository(session)).authenticate(
        payload.username,
        payload.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

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
