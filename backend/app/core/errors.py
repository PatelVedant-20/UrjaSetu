"""Error contract and exception handlers.

Every non-2xx response leaves the API in the locked envelope from
docs/05_API_SPEC.md:

    {"error": {"code": ..., "message": ..., "details": {}, "request_id": ...}}

Domain code raises `UrjaSetuError` subclasses; transport translation happens
here and only here.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class UrjaSetuError(Exception):
    """Base class for errors that carry a stable, client-facing code."""

    code = "INTERNAL_ERROR"
    message = "An unexpected error occurred."
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        self.http_status = http_status or self.http_status
        super().__init__(self.message)


class DatabaseUnavailableError(UrjaSetuError):
    """Raised when PostgreSQL cannot be reached or a session cannot be opened."""

    code = "DATABASE_UNAVAILABLE"
    message = "The database is not reachable."
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE


class ConfigurationError(UrjaSetuError):
    code = "CONFIGURATION_ERROR"
    message = "The application is misconfigured."
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR


def error_response(
    *,
    code: str,
    message: str,
    http_status: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the envelope. The single place the error shape is constructed."""
    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id_ctx.get(),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so no error path can bypass the envelope."""

    @app.exception_handler(UrjaSetuError)
    async def _handle_urjasetu_error(_: Request, exc: UrjaSetuError) -> JSONResponse:
        logger.warning("%s: %s", exc.code, exc.message)
        return error_response(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            details=exc.details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            code=_http_code_name(exc.status_code),
            message=str(exc.detail),
            http_status=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            code="REQUEST_VALIDATION_FAILED",
            message="Request payload failed validation.",
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            # `jsonable_encoder`-safe: Pydantic v2 errors can carry non-JSON values.
            details={"errors": _jsonable_validation_errors(exc)},
        )

    @app.exception_handler(SQLAlchemyError)
    async def _handle_sqlalchemy_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Driver messages can contain connection strings; never forward them.
        logger.exception("Unhandled database error")
        return error_response(
            code=DatabaseUnavailableError.code,
            message=DatabaseUnavailableError.message,
            http_status=DatabaseUnavailableError.http_status,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        return error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _jsonable_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for err in exc.errors():
        cleaned.append(
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "type": err.get("type", ""),
                "msg": err.get("msg", ""),
            }
        )
    return cleaned


_HTTP_CODE_NAMES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "REQUEST_VALIDATION_FAILED",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def _http_code_name(status_code: int) -> str:
    return _HTTP_CODE_NAMES.get(status_code, f"HTTP_{status_code}")
