"""Error response sanitizer — exception handlers that strip asyncpg messages,
stack traces, and provider response bodies from HTTP responses (REG-05 T294).

All 4xx/5xx responses return:
    {"error_code": <ErrorCode>, "message": <safe string>, "request_id": <uuid>}

The full error is logged server-side (with redaction filter from T288).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from fastapi import HTTPException

from .error_codes import ErrorCode

logger = logging.getLogger(__name__)

# Map HTTP status codes to safe ErrorCode values
_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.bad_request,
    401: ErrorCode.invalid_credentials,
    403: ErrorCode.forbidden,
    404: ErrorCode.not_found,
    422: ErrorCode.validation_error,
    429: ErrorCode.rate_limited,
    503: ErrorCode.service_unavailable,
}


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid.uuid4())


def _sanitized_json(
    *,
    status_code: int,
    error_code: ErrorCode,
    message: str,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code.value,
            "message": message,
            "request_id": request_id,
        },
    )


def structured_http_exception(
    status_code: int,
    error_code: ErrorCode,
    message: str,
    **extras: Any,
) -> HTTPException:
    """Build an HTTPException whose detail carries a structured error_code.

    Cycle Z5 B.1 helper. Routers that used to write
    ``raise HTTPException(409, detail={"error_code": "...", "message": "..."})``
    by hand can now write
    ``raise structured_http_exception(409, ErrorCode.four_gate_not_passed, "...")``
    and the handler below will extract the structured fields instead of
    stringifying the whole dict into the message body (which is the bug
    A.18 surfaced — the inner error_code was buried inside the outer
    "message" string).

    Extra keyword args (e.g. ``blocking_gates=[...]``) are carried through
    onto the response body so domain-specific context survives the
    sanitisation pass.
    """
    detail: dict[str, Any] = {"error_code": error_code.value, "message": message}
    detail.update(extras)
    return HTTPException(status_code=status_code, detail=detail)


def _coerce_error_code(value: Any) -> ErrorCode | None:
    """Return ErrorCode if value is a known enum value/name, else None."""
    if not isinstance(value, str):
        return None
    try:
        return ErrorCode(value)
    except ValueError:
        return None


async def http_exception_handler(request: Request, exc: Any) -> JSONResponse:
    """Sanitized handler for FastAPI HTTPException.

    If the handler raised ``structured_http_exception(...)`` (or directly
    set ``detail`` to a dict containing ``error_code`` / ``message`` keys),
    extract those fields verbatim. Otherwise fall back to the status-code
    → ErrorCode map and stringify ``detail`` as the message. 5xx details
    are always suppressed.
    """
    if not isinstance(exc, HTTPException):
        return await unhandled_exception_handler(request, exc)

    request_id = _request_id(request)
    fallback_code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.internal_error)

    structured_code: ErrorCode | None = None
    structured_message: str | None = None
    extras: dict[str, Any] = {}
    if isinstance(exc.detail, dict):
        structured_code = _coerce_error_code(exc.detail.get("error_code"))
        raw_msg = exc.detail.get("message")
        if isinstance(raw_msg, str):
            structured_message = raw_msg
        extras = {
            k: v for k, v in exc.detail.items()
            if k not in {"error_code", "message"}
        }

    if exc.status_code >= 500:
        logger.error(
            "HTTP %d [request_id=%s] %s %s: %s",
            exc.status_code, request_id, request.method, request.url.path, exc.detail,
        )
        message = "An internal error occurred"
        code = fallback_code
        extras = {}
    else:
        code = structured_code or fallback_code
        if structured_message is not None:
            message = structured_message
        elif exc.detail:
            message = str(exc.detail)
        else:
            message = code.value

    if extras:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": code.value,
                "message": message,
                "request_id": request_id,
                **extras,
            },
        )
    return _sanitized_json(
        status_code=exc.status_code,
        error_code=code,
        message=message,
        request_id=request_id,
    )


async def validation_exception_handler(request: Request, exc: Any) -> JSONResponse:
    """Sanitized handler for FastAPI RequestValidationError (422 + invalid path UUIDs).

    FastAPI's default emits a `{"detail": [...]}` shape without request_id, which
    breaks the sanitization contract (every error response must carry request_id).
    """
    request_id = _request_id(request)
    return _sanitized_json(
        status_code=422,
        error_code=ErrorCode.validation_error,
        message="Request validation failed",
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Any) -> JSONResponse:
    """Catch-all 500 handler — logs full traceback, returns only error_code.

    Strips asyncpg exception messages, provider response bodies, and stack
    traces from the client response.
    """
    request_id = _request_id(request)
    exc_type = type(exc).__name__

    # Log full exception server-side (redaction filter from T288 will mask secrets)
    logger.exception(
        "Unhandled %s [request_id=%s] %s %s",
        exc_type, request_id, request.method, request.url.path,
        exc_info=exc,
    )

    return _sanitized_json(
        status_code=500,
        error_code=ErrorCode.internal_error,
        message="An internal error occurred",
        request_id=request_id,
    )


async def asyncpg_exception_handler(request: Request, exc: Any) -> JSONResponse:
    """Catch asyncpg exceptions — never expose SQL error messages to clients."""
    request_id = _request_id(request)
    logger.error(
        "Database error %s [request_id=%s] %s %s",
        type(exc).__name__, request_id, request.method, request.url.path,
    )
    return _sanitized_json(
        status_code=500,
        error_code=ErrorCode.internal_error,
        message="A database error occurred",
        request_id=request_id,
    )
