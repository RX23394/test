"""Application health endpoint."""

from fastapi import APIRouter

from app.schemas.response import ResponseModel

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=ResponseModel[None],
    response_model_exclude_none=True,
)
async def health_check() -> ResponseModel[None]:
    """Return the application health status."""
    return ResponseModel(status="ok")
