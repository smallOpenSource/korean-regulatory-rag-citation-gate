"""Security middleware registration helper (REG-05 T284/T286/T288/T292/T294/T295).

Call ``register_security_middleware(app, config)`` from ``main.py`` **after**
FastAPI app creation but **before** any request is served.

Middleware execution order (outermost → innermost, per Starlette stack semantics):
    SecurityHeadersMiddleware   → HTTP security headers on every response (T284)
    HttpsEnforceMiddleware      → HTTP→HTTPS redirect via X-Forwarded-Proto (T295)
    GlobalRateLimitMiddleware   → per-IP 600 req/min; /docs 10 req/min (T292)
    CorsGuardMiddleware         → explicit 403 on disallowed Origin (T286)
    [CORSMiddleware]            → standard preflight handling (registered in main.py)
    [application routes / exception handlers]
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from .config import AppConfig
from .error_codes import ErrorCode
from .errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from .https_enforce import HttpsEnforceMiddleware
from .rate_limit import check_global_rate_limit
from .redaction import configure_logging_redaction
from .security_headers import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


def _extract_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", "unknown") if client else "unknown"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CORS Guard (T286)
# ---------------------------------------------------------------------------

class CorsGuardMiddleware(BaseHTTPMiddleware):
    """Explicitly reject requests with a disallowed Origin header (REG-05 T286).

    FastAPI's CORSMiddleware silently omits CORS headers on mismatched origins
    but does not return an error. This guard makes the rejection explicit (403)
    when CORS is enabled and an Origin header is present but not in the allowlist.
    """

    def __init__(self, app: ASGIApp, *, allowed_origins: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin", "").strip()
        if origin and self._allowed_origins and origin not in self._allowed_origins:
            logger.warning(
                "CORS guard: rejected disallowed Origin %r for %s %s",
                origin, request.method, request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": ErrorCode.forbidden.value,
                    "message": "Origin not allowed",
                    "request_id": request.headers.get("x-request-id", ""),
                },
            )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Global Rate Limit (T292)
# ---------------------------------------------------------------------------

class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP global rate limit for all API routes (REG-05 T292).

    Limits:
    - /health, /metrics: exempt (no limit — load-balancer probes)
    - /docs, /redoc, /openapi.json: 10 req/min
    - All other routes: 600 req/min

    On limit exceeded: 429 with ``Retry-After`` header.
    Audit event ``rate_limit_exceeded`` is written best-effort (no Redis = fail open).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        redis = getattr(request.app.state, "async_redis_client", None)
        if redis is None:
            # Redis unavailable → fail open for global limit (auth endpoints fail closed)
            return await call_next(request)

        ip = _extract_ip(request)
        path = request.url.path

        try:
            allowed, retry_after = await check_global_rate_limit(redis, ip=ip, path=path)
        except Exception as exc:  # noqa: BLE001 — Redis transient failure must not 500
            # Includes redis.exceptions.ConnectionError / TimeoutError / RedisError plus
            # built-in ConnectionError / OSError if the socket layer fails before redis-py wraps it.
            # T292 rate-limit is DoS mitigation; auth (JWT/password) still runs downstream.
            logger.warning(
                "GlobalRateLimit fail-open: Redis call failed (%s: %s) — request allowed through",
                type(exc).__name__, exc,
            )
            return await call_next(request)
        if not allowed:
            await _try_audit_rate_limit(request, ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": ErrorCode.rate_limited.value,
                    "message": "Too many requests",
                    "request_id": request.headers.get("x-request-id", ""),
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


async def _try_audit_rate_limit(request: Request, ip: str, path: str) -> None:
    """Best-effort audit write for global rate limit exceed events (T292)."""
    try:
        from ..repositories import audit as audit_repo  # noqa: PLC0415

        pool = getattr(request.app.state, "pool", None)
        if pool is None:
            return
        async with pool.acquire() as conn:
            await audit_repo.insert_audit_log(
                conn,
                actor_id=None,
                action_code="rate_limit_exceeded",
                resource_type="api",
                resource_id=None,
                detail={"ip_hash": _short_hash(ip), "path": path},
                ip_address=ip,
                user_agent=request.headers.get("user-agent"),
            )
    except Exception:  # noqa: BLE001 — audit failure must not affect the 429 response
        logger.debug("rate_limit_exceeded audit write failed (best-effort)")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_security_middleware(app: FastAPI, config: AppConfig) -> None:
    """Register all security middlewares and exception handlers on *app*.

    Must be called after CORSMiddleware is added. Middlewares wrap in reverse
    registration order, so the LAST ``add_middleware`` call is outermost.

    T284: SecurityHeadersMiddleware — HTTP security headers on every response.
    T286: CorsGuardMiddleware — explicit 403 on disallowed Origin.
    T288: configure_logging_redaction() — global logging filter installed here.
    T292: GlobalRateLimitMiddleware — per-IP 600 req/min global limit.
    T294: exception handlers — sanitize asyncpg errors, stack traces, 500s.
    T295: HttpsEnforceMiddleware — 308 redirect for HTTP requests in non-dev.
    """
    # T288 — install redaction filter before any request is processed
    configure_logging_redaction()

    # T294 — exception handlers (innermost; run before middleware unwraps)
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    app.add_exception_handler(
        HTTPException,  # type: ignore[arg-type]
        http_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RequestValidationError,  # type: ignore[arg-type]
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        Exception,  # type: ignore[arg-type]
        unhandled_exception_handler,  # type: ignore[arg-type]
    )

    # T286 — CORS guard (inner of rate-limit, outer of CORSMiddleware)
    if config.cors.enabled and config.cors.allowed_origins:
        allowed: frozenset[str] = frozenset(config.cors.allowed_origins)
        app.add_middleware(CorsGuardMiddleware, allowed_origins=allowed)

    # T292 — global rate limit (outer of CORS guard)
    app.add_middleware(GlobalRateLimitMiddleware)

    # T295 — HTTPS enforcement (outer of rate limit)
    app.add_middleware(HttpsEnforceMiddleware, app_env=config.runtime.app_env)

    # T284 — security headers outermost so they cover every response
    app.add_middleware(SecurityHeadersMiddleware)
