"""Consistent error mapping for API routes."""

from uuid import UUID

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from groq import GroqError, RateLimitError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.schemas import ErrorResponse


def _request_id(request: Request) -> UUID:
    return request.state.request_id


def _payload(request: Request, code: str, message: str, details=None) -> dict:
    return ErrorResponse(
        error={
            "code": code,
            "message": message,
            "request_id": _request_id(request),
            "details": details,
        }
    ).model_dump(mode="json")


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"location": list(error.get("loc", ())), "message": error.get("msg", "Invalid value")}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_payload(request, "invalid_request", "Request validation failed", details),
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "context_window_exceeded" if exc.status_code == 413 else "http_error"
    message = str(exc.detail) if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=_payload(request, code, message),
    )


async def groq_error_handler(request: Request, exc: GroqError) -> JSONResponse:
    if isinstance(exc, RateLimitError):
        status_code, code, message = 429, "provider_rate_limited", "The model provider is rate limiting requests"
    else:
        status_code, code, message = 502, "provider_unavailable", "The model provider could not complete the request"
    return JSONResponse(
        status_code=status_code,
        content=_payload(request, code, message),
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Avoid putting exception text in logs or responses; SDK exceptions may
    # contain request metadata that should not be exposed.
    return JSONResponse(
        status_code=500,
        content=_payload(request, "internal_error", "An unexpected server error occurred"),
    )
