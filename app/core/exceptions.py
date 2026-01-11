"""Custom exceptions and exception handlers."""

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found exception."""

    def __init__(self, resource: str, identifier: str | None = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


class ValidationException(AppException):
    """Validation error exception."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class ConflictException(AppException):
    """Resource conflict exception."""

    def __init__(self, message: str):
        super().__init__(message, status_code=status.HTTP_409_CONFLICT)


class DatabaseException(AppException):
    """Database operation exception."""

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExternalServiceException(AppException):
    """External service error exception."""

    def __init__(self, service: str, message: str | None = None):
        msg = f"External service '{service}' unavailable"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(msg, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    # Log the exception (in production, use proper logging)
    print(f"Unexpected error: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "An unexpected error occurred",
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
