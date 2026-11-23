"""chaos_guard.py — Chaos-engineering endpoint guard (REG-06 §5, ADR-004).

Blocks any "chaos engineering" path in production profiles while allowing
a closed whitelist of demo-only chaos toggles in PoC environments.

Chaos endpoints are any paths that:
  - Inject artificial faults or latency
  - Toggle failure modes for testing purposes
  - Reset / corrupt in-flight state for chaos-testing

In production (APP_ENV not in {poc, poc-internet, poc-staging}), ALL chaos
paths are blocked unconditionally.  In PoC environments only the explicitly
whitelisted paths below are allowed; anything not on the whitelist is still
blocked.

Usage (FastAPI middleware or per-route dependency):

    from apps.api.harness.core.chaos_guard import ChaosGuard

    guard = ChaosGuard.from_env()

    # In an endpoint:
    guard.require_allowed(request.url.path)

    # As a middleware factory:
    app.middleware("http")(guard.as_middleware())

REG-06 §5 note: the whitelist is intentionally small and reviewed per demo
sprint.  Adding an entry requires an ADR-004 amendment (comment
``# ADR-004-exempt`` next to the entry and a reference ticket).
"""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POC_ENVS: frozenset[str] = frozenset({"poc", "poc-internet", "poc-staging"})

# Demo-only chaos toggles whitelisted per REG-06 §5 / ADR-004.
# Each entry is a regex pattern matched against the full request path.
# ANY path NOT matching one of these is blocked even in PoC environments.
#
# Format: (pattern_str, description, exemption_ticket)
_WHITELIST_RAW: tuple[tuple[str, str, str], ...] = (
    (
        r"^/demo/chaos/latency$",
        "Artificial latency injection for demo load tests",
        "ADR-004-exempt:T-chaos-01",
    ),
    (
        r"^/demo/chaos/fail-rate$",
        "Configurable failure-rate toggle for PoC abort threshold tests",
        "ADR-004-exempt:T-chaos-02",
    ),
    (
        r"^/demo/chaos/demo-mode-expire$",
        "Force-expire the demo_mode flag for expiry scenario tests (S09)",
        "ADR-004-exempt:T-chaos-03",
    ),
    (
        r"^/demo/chaos/rate-limit-reset$",
        "Reset per-employee Redis rate counters for S10 scenario tests",
        "ADR-004-exempt:T-chaos-04",
    ),
    (
        r"^/demo/chaos/abort-threshold-reset$",
        "Reset the abort threshold counter for S11 scenario tests",
        "ADR-004-exempt:T-chaos-05",
    ),
)

# Patterns that flag a request path as a chaos endpoint (even outside /demo/chaos/).
# These must ALWAYS be blocked in production, with no whitelist override.
_CHAOS_PATH_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"/chaos/",
        r"/fault[_-]inject",
        r"/latency[_-]inject",
        r"/kill[_-]switch",
        r"/blackhole",
        r"/toxic[_-]proxy",
        r"/_chaos$",
        r"/demo/chaos/",
    )
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WhitelistEntry:
    pattern: re.Pattern[str]
    description: str
    exemption_ticket: str


@dataclass(frozen=True)
class ChaosCheckResult:
    """Result of a single chaos path check."""

    path: str
    is_chaos_path: bool
    is_whitelisted: bool
    blocked: bool
    reason: str
    env: str

    @property
    def allowed(self) -> bool:
        return not self.blocked


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


@dataclass
class ChaosGuard:
    """Stateless chaos-engineering endpoint guard.

    Instantiate via :meth:`ChaosGuard.from_env` for production use or
    :meth:`ChaosGuard.for_env` in tests.
    """

    app_env: str
    whitelist: tuple[WhitelistEntry, ...] = field(
        default_factory=lambda: ChaosGuard._build_whitelist()
    )

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "ChaosGuard":
        """Create a guard reading APP_ENV from the process environment."""
        app_env = os.environ.get("APP_ENV", "").strip().lower()
        return cls(app_env=app_env)

    @classmethod
    def for_env(cls, app_env: str) -> "ChaosGuard":
        """Create a guard for a specific environment (useful in tests)."""
        return cls(app_env=app_env.strip().lower())

    @staticmethod
    def _build_whitelist() -> tuple[WhitelistEntry, ...]:
        return tuple(
            WhitelistEntry(
                pattern=re.compile(pattern, re.IGNORECASE),
                description=desc,
                exemption_ticket=ticket,
            )
            for pattern, desc, ticket in _WHITELIST_RAW
        )

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    @property
    def is_poc_env(self) -> bool:
        """True when the current environment is a PoC variant."""
        return self.app_env in POC_ENVS

    def _is_chaos_path(self, path: str) -> bool:
        """Return True when path looks like a chaos/fault-injection endpoint."""
        return any(p.search(path) for p in _CHAOS_PATH_PATTERNS)

    def _is_whitelisted(self, path: str) -> WhitelistEntry | None:
        """Return the matching whitelist entry or None."""
        for entry in self.whitelist:
            if entry.pattern.match(path):
                return entry
        return None

    def check(self, path: str) -> ChaosCheckResult:
        """Evaluate whether ``path`` should be allowed.

        Rules:
          1. If not a chaos path → allowed (guard is a no-op).
          2. If production env → always blocked (no whitelist).
          3. If PoC env and path on whitelist → allowed.
          4. Otherwise → blocked.
        """
        is_chaos = self._is_chaos_path(path)

        if not is_chaos:
            return ChaosCheckResult(
                path=path,
                is_chaos_path=False,
                is_whitelisted=False,
                blocked=False,
                reason="not_a_chaos_path",
                env=self.app_env,
            )

        if not self.is_poc_env:
            return ChaosCheckResult(
                path=path,
                is_chaos_path=True,
                is_whitelisted=False,
                blocked=True,
                reason=(
                    f"chaos_endpoints_blocked_in_production:"
                    f"env={self.app_env or 'unset'}"
                ),
                env=self.app_env,
            )

        entry = self._is_whitelisted(path)
        if entry is not None:
            return ChaosCheckResult(
                path=path,
                is_chaos_path=True,
                is_whitelisted=True,
                blocked=False,
                reason=f"poc_demo_whitelist:{entry.exemption_ticket}",
                env=self.app_env,
            )

        return ChaosCheckResult(
            path=path,
            is_chaos_path=True,
            is_whitelisted=False,
            blocked=True,
            reason="chaos_path_not_on_poc_whitelist",
            env=self.app_env,
        )

    def require_allowed(self, path: str) -> None:
        """Raise ``RuntimeError`` when the path should be blocked.

        Call from FastAPI route handlers or dependency injection:

            guard.require_allowed(request.url.path)
        """
        result = self.check(path)
        if result.blocked:
            raise RuntimeError(
                f"ChaosGuard: path {path!r} blocked — {result.reason}"
            )

    # ------------------------------------------------------------------
    # FastAPI middleware integration
    # ------------------------------------------------------------------

    def as_middleware(
        self,
    ) -> Callable[..., Awaitable[Any]]:
        """Return an ASGI middleware callable for use with ``app.middleware('http')``."""

        guard = self

        async def _middleware(
            request: Any,
            call_next: Callable[..., Awaitable[Any]],
        ) -> Any:
            path: str = getattr(request, "url", None) and str(request.url.path) or ""
            result = guard.check(path)
            if result.blocked:
                from fastapi.responses import JSONResponse  # local import to avoid hard dep

                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "chaos_endpoint_blocked",
                        "reason": result.reason,
                        "env": result.env,
                    },
                )
            return await call_next(request)

        return _middleware  # type: ignore[return-value]
