"""HTTP security headers ASGI middleware (REG-05 T284).

Adds hardened security headers to every response. The CSP ``script-src``
placeholder leaves room for the SRI sha256 hash added in T285/T295 (task #13).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Content-Security-Policy — relaxed for local PoC; sha256 hash injected in task #13 (SRI).
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # shadcn/ui requires unsafe-inline for now
    "img-src 'self' data:; "
    "connect-src 'self' wss://*; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

_SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=15552000; includeSubDomains; preload",
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Append HTTP security headers to every response (REG-05 T284).

    Placed outermost in the middleware stack so headers are added regardless of
    which inner middleware or handler produces the response.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response
