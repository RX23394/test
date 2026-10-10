"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from app.api.pagination import TOTAL_COUNT_HEADER
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging()
    application = FastAPI(title=settings.app_name, debug=settings.app_debug)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Pagination totals are exposed to the browser, which can only read
        # headers listed here on a cross-origin response.
        expose_headers=[TOTAL_COUNT_HEADER],
    )
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.include_router(api_router)
    return application


app = create_app()
