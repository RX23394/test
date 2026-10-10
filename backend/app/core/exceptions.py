"""Application exception handlers."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.response import ResponseModel

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Internal server error"


async def http_exception_handler(
    request: Request,
    exception: HTTPException,
) -> JSONResponse:
    """Convert HTTP exceptions to the uniform API response model."""
    del request
    payload = ResponseModel[None](
        status="error",
        message=str(exception.detail),
    )
    return JSONResponse(
        status_code=exception.status_code,
        content=payload.model_dump(exclude_none=True),
        headers=exception.headers,
    )


async def unhandled_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Convert unexpected errors to the uniform response model.

    The traceback is written to the application log only; the response body
    never leaks internal details.
    """
    logger.error(
        "Unhandled error while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exception,
    )
    payload = ResponseModel[None](
        status="error",
        message=INTERNAL_ERROR_MESSAGE,
    )
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(exclude_none=True),
    )


async def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Convert request validation errors to the uniform response model."""
    del request, exception
    payload = ResponseModel[None](
        status="error",
        message="Request validation failed",
    )
    return JSONResponse(
        status_code=422,
        content=payload.model_dump(exclude_none=True),
    )
