"""Administrator user-management endpoints."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import CurrentAdmin, SessionDependency
from app.auth.security import hash_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ManagedUserCreate,
    ManagedUserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.schemas.response import ResponseModel

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.get(
    "",
    response_model=ResponseModel[list[ManagedUserResponse]],
    response_model_exclude_none=True,
)
def list_users(
    current_admin: CurrentAdmin,
    session: SessionDependency,
) -> ResponseModel[list[ManagedUserResponse]]:
    """List all user accounts for an administrator."""
    del current_admin
    users = UserRepository(session).list_all()
    return ResponseModel(
        status="ok",
        data=[ManagedUserResponse.model_validate(user) for user in users],
    )


@router.post(
    "",
    response_model=ResponseModel[ManagedUserResponse],
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: ManagedUserCreate,
    current_admin: CurrentAdmin,
    session: SessionDependency,
) -> ResponseModel[ManagedUserResponse]:
    """Create an active administrator or standard user account."""
    del current_admin
    try:
        user = UserRepository(session).create(
            username=payload.username,
            password_hash=hash_password(payload.password),
            is_admin=payload.role == "admin",
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        ) from exc
    return ResponseModel(
        status="ok",
        data=ManagedUserResponse.model_validate(user),
    )


@router.patch(
    "/{user_id}/status",
    response_model=ResponseModel[ManagedUserResponse],
    response_model_exclude_none=True,
)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    current_admin: CurrentAdmin,
    session: SessionDependency,
) -> ResponseModel[ManagedUserResponse]:
    """Deactivate or reactivate a user account."""
    repository = UserRepository(session)
    user = _require_user(repository, user_id)
    if user.id == current_admin.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Administrators cannot deactivate themselves",
        )
    updated_user = repository.update_active(user, payload.is_active)
    return ResponseModel(
        status="ok",
        data=ManagedUserResponse.model_validate(updated_user),
    )


@router.patch(
    "/{user_id}/role",
    response_model=ResponseModel[ManagedUserResponse],
    response_model_exclude_none=True,
)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    current_admin: CurrentAdmin,
    session: SessionDependency,
) -> ResponseModel[ManagedUserResponse]:
    """Assign the administrator or standard user role."""
    repository = UserRepository(session)
    user = _require_user(repository, user_id)
    if user.id == current_admin.id and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Administrators cannot remove their own role",
        )
    updated_user = repository.update_admin(user, payload.role == "admin")
    return ResponseModel(
        status="ok",
        data=ManagedUserResponse.model_validate(updated_user),
    )


def _require_user(repository: UserRepository, user_id: int) -> User:
    """Return one managed user or raise an HTTP not-found response."""
    user = repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
