"""HTTPS enforcement middleware via X-Forwarded-Proto header (REG-05 T295).

In non-development profiles, non-HTTPS requests are redirected with 308
(Permanent Redirect) so clients update their bookmarks and follow the redirect
with the same method. Health check paths are exempt for load-balancer probes.

nginx must be configured to set ``X-Forwarded-Proto: https`` when terminating
TLS (see docs/runbooks/RUN-04_https_setup.md).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Paths that load-balancer probes hit over plain HTTP — always exempt
_EXEMPT_PREFIXES: tuple[str, ...] = ("/health", "/metrics")

# APP_ENV values that are considered development (no HTTPS enforcement)
_DEV_ENVS: frozenset[str] = frozenset({"development", "dev", "local", "test"})


class HttpsEnforceMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP→HTTPS using the ``X-Forwarded-Proto`` header (REG-05 T295).

    Enabled only when ``app_env`` is not a development/test profile.
    Responds with HTTP 308 so the client re-issues the same method over HTTPS.
    """

    def __init__(self, app: ASGIApp, *, app_env: str) -> None:
        super().__init__(app)
        self._enforce = app_env not in _DEV_ENVS

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._enforce:
            return await call_next(request)

        # Exempt paths (health probes from load balancer over plain HTTP)
        path = request.url.path
        if any(path == p or path.startswith(f"{p}/") for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        proto = request.headers.get("x-forwarded-proto", "").strip().lower()
        if proto and proto != "https":
            https_url = str(request.url).replace("http://", "https://", 1)
            return Response(
                status_code=308,
                headers={"Location": https_url},
            )

        return await call_next(request)
