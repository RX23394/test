"""Application exception handlers."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.pagination import TOTAL_COUNT_HEADER
from app.core.config import get_settings
from app.rag.dependencies import EMBEDDING_UNAVAILABLE_MESSAGE
from app.schemas.response import ResponseModel

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Internal server error"


def cors_error_headers(request: Request) -> dict[str, str]:
    """Return CORS headers for a response the CORS middleware never sees.

    ``ServerErrorMiddleware`` is the outermost layer of the stack, so the 500 it
    produces for an unhandled exception is sent on the raw ASGI ``send`` and
    bypasses ``CORSMiddleware`` entirely. A cross-origin browser then rejects
    that response for *every* endpoint, and ``fetch`` reports only
    "Failed to fetch" -- the real status and message never reach the client.
    Reproducing the headers here keeps the uniform error contract readable.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return {}
    settings = get_settings()
    if origin not in settings.cors_allow_origins:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Expose-Headers": TOTAL_COUNT_HEADER,
        "Vary": "Origin",
    }


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
        headers=cors_error_headers(request),
    )


async def embedding_unavailable_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Report a missing encoder as an unavailable service, not a server fault.

    The encoder is resolved as a dependency, which runs before any route's own
    error handling. A machine that cannot obtain the model is an operational
    condition the client can act on, so it must not surface as an opaque 500.
    """
    logger.error(
        "Embedding model unavailable while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exception,
    )
    payload = ResponseModel[None](
        status="error",
        message=EMBEDDING_UNAVAILABLE_MESSAGE,
    )
    return JSONResponse(
        status_code=503,
        content=payload.model_dump(exclude_none=True),
        headers=cors_error_headers(request),
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
