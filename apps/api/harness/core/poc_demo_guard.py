"""PoC_AUTO_APPROVAL 3-layer attestation primitives (ADR-004, REG-06 §3 / §5).

This module provides the *atomic* checks for the three trust layers and the
fail-closed production guard. Service-level orchestration (rate limiting,
abort conditions, expiry warnings) lives in
:mod:`apps.api.harness.services.poc_auto_approval`.

Layers (all must be true for ``allowed=True``):
    A — Build-time env var ``POC_AUTO_APPROVAL_ENABLED=true``
    B — DB ``system_flags.demo_mode.flag_value['enabled'] = true`` AND not expired
    C — HTTP request header ``X-Poc-Demo-Mode: true``

Any single layer false → ``allowed=False`` and the request must fall through
to the human-approval path. Production builds dead-code-eliminate this module
and the production guard ``prod_guard_block_in_prod()`` is the fixed-constant
``true`` recorded on every auto-approve audit row (REG-06 §3.2,
ADR-004 §"gate_evidence_json Schema" invariant 4).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

LAYER_A_ENV_VAR = "POC_AUTO_APPROVAL_ENABLED"
LAYER_C_HEADER = "X-Poc-Demo-Mode"
LAYER_C_HEADER_LOWER = LAYER_C_HEADER.lower()
DEMO_MODE_FLAG_NAME = "demo_mode"
DEMO_MODE_CEILING_HOURS = 8
DEMO_MODE_PRE_WARNING_MINUTES = 5

GOVERNANCE_MARKER_POC = "PoC_AUTO_APPROVAL"
GOVERNANCE_MARKER_HUMAN = "HUMAN_REVIEW"

# Fixed constant per ADR-004 invariant 4: every auto-approve audit row records
# prod_guard.would_block_in_prod=true. Drift fails the validator suite (ADR-007).
PROD_GUARD_WOULD_BLOCK_IN_PROD: bool = True


@dataclass(frozen=True)
class AutoApproveContext:
    """Result of evaluating the three-layer attestation for one request."""

    allowed: bool
    governance_marker: str
    layer_a: bool
    layer_b: bool
    layer_c: bool
    reason_code: str | None = None
    demo_mode_expires_at: datetime | None = None
    layer_b_attested_by: str | None = None
    prod_guard: dict[str, Any] = field(
        default_factory=lambda: {
            "would_block_in_prod": PROD_GUARD_WOULD_BLOCK_IN_PROD,
            "guard_env_var": LAYER_A_ENV_VAR,
        }
    )

    @property
    def fixed_prod_guard(self) -> dict[str, Any]:
        """Return the audit ``prod_guard`` subtree (fixed constant, ADR-004 §4)."""
        return {
            "would_block_in_prod": PROD_GUARD_WOULD_BLOCK_IN_PROD,
            "guard_env_var": LAYER_A_ENV_VAR,
        }


def is_layer_a_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Layer A: ``POC_AUTO_APPROVAL_ENABLED=true`` build-time env var.

    Resolution is case-insensitive but only the literal string ``"true"``
    (after lowercasing) is honored — empty/unset/anything else → False.
    Production builds must ship with this variable unset.
    """
    source = env if env is not None else os.environ
    raw = str(source.get(LAYER_A_ENV_VAR, "")).strip().lower()
    return raw == "true"


def check_layer_c_header(headers: Mapping[str, str] | None) -> bool:
    """Layer C: incoming request must carry ``X-Poc-Demo-Mode: true``.

    Header lookup is case-insensitive (FastAPI ``request.headers`` already
    does this, but this helper also tolerates raw dicts from tests).
    """
    if headers is None:
        return False
    raw: Any = None
    if hasattr(headers, "get"):
        raw = headers.get(LAYER_C_HEADER)
    if raw is None:
        for key, value in headers.items():
            if str(key).lower() == LAYER_C_HEADER_LOWER:
                raw = value
                break
    return str(raw or "").strip().lower() == "true"


def _parse_iso8601(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def evaluate_demo_mode_flag(
    flag_value: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, datetime | None, str | None]:
    """Evaluate ``system_flags.demo_mode.flag_value`` (Layer B core check).

    Returns ``(enabled, expires_at, attested_by)``. ``enabled`` is True only
    when ``flag_value['enabled'] is True`` AND ``expires_at > now`` AND no
    ``aborted_at`` is set (auto-OFF abort condition, ADR-004 §4).
    """
    if not isinstance(flag_value, Mapping):
        return False, None, None
    if not bool(flag_value.get("enabled", False)):
        return False, None, None
    if flag_value.get("aborted_at"):
        return False, None, None
    expires_at = _parse_iso8601(flag_value.get("expires_at"))
    if expires_at is None:
        return False, None, None
    reference = now or datetime.now(tz=timezone.utc)
    if expires_at <= reference:
        return False, expires_at, None
    attested_by = flag_value.get("toggled_on_by") or flag_value.get("attested_by")
    return True, expires_at, str(attested_by) if attested_by else None


def attestation_reason_code(
    *, layer_a: bool, layer_b: bool, layer_c: bool
) -> str | None:
    """Return a stable reason_code identifying which attestation layer failed."""
    if layer_a and layer_b and layer_c:
        return None
    missing: list[str] = []
    if not layer_a:
        missing.append("env")
    if not layer_b:
        missing.append("db")
    if not layer_c:
        missing.append("header")
    return f"poc_auto_approval_layer_missing:{'|'.join(missing)}"


def build_auto_approve_context(
    *,
    layer_a: bool,
    layer_b: bool,
    layer_c: bool,
    expires_at: datetime | None = None,
    attested_by: str | None = None,
) -> AutoApproveContext:
    """Aggregate three layer booleans into an :class:`AutoApproveContext`.

    On any failed layer the governance_marker stays ``HUMAN_REVIEW`` and the
    request must follow the human-approval path. Only when all three are
    True is the marker upgraded to ``PoC_AUTO_APPROVAL``.
    """
    allowed = bool(layer_a and layer_b and layer_c)
    return AutoApproveContext(
        allowed=allowed,
        governance_marker=GOVERNANCE_MARKER_POC if allowed else GOVERNANCE_MARKER_HUMAN,
        layer_a=layer_a,
        layer_b=layer_b,
        layer_c=layer_c,
        reason_code=attestation_reason_code(
            layer_a=layer_a, layer_b=layer_b, layer_c=layer_c
        ),
        demo_mode_expires_at=expires_at if allowed else None,
        layer_b_attested_by=attested_by if allowed else None,
    )


def prod_guard_block_in_prod(app_env: str | None) -> bool:
    """Fixed-constant production guard (ADR-004 §"Dead-Code Elimination").

    Returns True (i.e. *block*) when the runtime is not the PoC environment.
    Routes that import the auto-approval handler must call this *before*
    granting auto-approval; the fixed-constant ``True`` keeps audit rows
    statically verifiable against the ADR-007 validator contract.
    """
    if not app_env:
        return True
    env_normalized = app_env.strip().lower()
    # Only the explicit "poc" environments may run the auto-approval path.
    return env_normalized not in {"poc", "poc-internet", "poc-staging"}
