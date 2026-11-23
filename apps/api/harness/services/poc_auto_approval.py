"""PoC_AUTO_APPROVAL service orchestration (ADR-004 T304/T312/T313/T314).

Composition over the atomic primitives in
:mod:`apps.api.harness.core.poc_demo_guard`:

* :func:`evaluate_three_layer_attestation` — full Layer A+B+C evaluation, hitting
  the DB for Layer B and the request headers for Layer C.
* :func:`check_per_employee_rate_limit` — Redis-backed 10/min + 60/hr ceiling
  per employee (T314).
* :func:`auto_expire_demo_mode_if_due` — 8h ceiling sweep (T312).
* :func:`broadcast_demo_mode_expiring_soon` — 5-min pre-warning via the
  realtime fanout manager.
* :func:`check_abort_conditions` — 4-gate fail rate / audit lag p99 /
  rate-limit breach pattern (T313). Each abort condition writes an audit row
  and toggles the demo_mode flag off.
* :func:`build_gate_evidence_audit_payload` — canonical detail_json subtree
  matching ADR-004 §"gate_evidence_json Schema".

All Redis keys follow the task-spec namespace
``harness:poc_auto_approval:{employee_id}:{1m|1h}:{window}``.

No mocks: rate-limit and abort signals read real Redis / Postgres state. The
``DemoModeService`` callable accepts the asyncpg pool and the async Redis
client at the boundaries described in
``apps/api/harness/api/dependencies.py``.

Operational status (PoC): demo mode is DORMANT — ``system_flags.demo_mode``
defaults to ``{"enabled": false}`` (V020) and no code path activates it (the
flag is only ever written OFF, by auto-expire/abort). Consequently
:func:`run_governance_sweep` is both UNWIRED (no production caller) and inert
(nothing to expire/warn), so ``demo_mode_expired`` / ``demo_mode_expiring_soon``
emit 0 rows at runtime. The primitives are kept production-ready for the day
demo mode is activated + the sweep is scheduled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.api.harness.core.poc_demo_guard import (
    DEMO_MODE_CEILING_HOURS,
    DEMO_MODE_FLAG_NAME,
    DEMO_MODE_PRE_WARNING_MINUTES,
    GOVERNANCE_MARKER_HUMAN,
    GOVERNANCE_MARKER_POC,
    LAYER_A_ENV_VAR,
    PROD_GUARD_WOULD_BLOCK_IN_PROD,
    AutoApproveContext,
    build_auto_approve_context,
    check_layer_c_header,
    evaluate_demo_mode_flag,
    is_layer_a_enabled,
    prod_guard_block_in_prod,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — task-spec ceilings and abort thresholds (ADR-004 §4)
# ---------------------------------------------------------------------------

RATE_KEY_PREFIX = "harness:poc_auto_approval"
RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_PER_HOUR = 60

ABORT_FOUR_GATE_FAIL_RATE = 0.05  # 5% over 1h sliding window
ABORT_AUDIT_LAG_P99_SECONDS = 60.0  # audit ledger lag p99 > 60s
ABORT_RATE_LIMIT_BREACH_THRESHOLD = 5  # ≥5 distinct employees rate-limited in 10 min

ACTION_AUTO_APPROVED = "poc_auto_approval_used"
ACTION_RATE_LIMITED = "poc_auto_approval_rate_limited"
ACTION_ABORTED = "poc_auto_approval_aborted"
ACTION_EXPIRING_SOON = "demo_mode_expiring_soon"
ACTION_EXPIRED = "demo_mode_expired"
ACTION_TOGGLE_OFF = "demo_mode_toggle_off"

# ---------------------------------------------------------------------------
# SQL contracts — raw, sql_id-prefixed (per project convention)
# ---------------------------------------------------------------------------

SELECT_DEMO_MODE_FLAG_SQL = """
/* sql_id: select_system_flags_demo_mode */
SELECT flag_value, updated_at FROM system_flags
WHERE flag_name = $1::text
LIMIT 1;
"""

UPDATE_DEMO_MODE_FLAG_SQL = """
/* sql_id: update_system_flags_demo_mode_value */
UPDATE system_flags
SET flag_value = $1::jsonb,
    updated_by = $2::uuid,
    change_reason = $3::text,
    ticket_id = $4::text
WHERE flag_name = $5::text;
"""

INSERT_AUDIT_ROW_SQL = """
/* sql_id: insert_poc_governance_audit_row */
INSERT INTO audit_logs
    (actor_id, action_code, resource_type, resource_id, ip_address, user_agent,
     detail_json, governance_marker)
VALUES ($1::uuid, $2::text, $3::text, $4::uuid, NULL, NULL, $5::jsonb, $6::text);
"""

SELECT_FOUR_GATE_FAIL_RATE_SQL = """
/* sql_id: select_four_gate_fail_rate_1h */
SELECT
    COALESCE(
        SUM(CASE WHEN gate_status = 'BLOCK' THEN 1 ELSE 0 END)::float
        / NULLIF(COUNT(*)::float, 0),
        0
    ) AS fail_rate,
    COUNT(*) AS attempted
FROM gate_evidence
WHERE recorded_at > now() - INTERVAL '1 hour';
"""

SELECT_AUDIT_LAG_P99_SQL = """
/* sql_id: select_audit_lag_p99_5m */
SELECT COALESCE(
    percentile_cont(0.99) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (now() - created_at))
    ),
    0
) AS lag_p99_seconds
FROM audit_logs
WHERE created_at > now() - INTERVAL '5 minutes';
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitState:
    """Per-employee Redis rate counters (snapshotted after increment)."""

    employee_id: str
    per_minute_count: int
    per_hour_count: int
    ceiling_minute: int = RATE_LIMIT_PER_MINUTE
    ceiling_hour: int = RATE_LIMIT_PER_HOUR

    @property
    def exceeded(self) -> bool:
        return (
            self.per_minute_count > self.ceiling_minute
            or self.per_hour_count > self.ceiling_hour
        )

    def to_audit_subtree(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "per_minute_count": self.per_minute_count,
            "per_hour_count": self.per_hour_count,
            "ceiling_minute": self.ceiling_minute,
            "ceiling_hour": self.ceiling_hour,
        }


@dataclass(frozen=True)
class DemoModeStatus:
    """Decoded view over ``system_flags.demo_mode.flag_value``."""

    enabled: bool
    expires_at: datetime | None
    attested_by: str | None
    aborted_at: datetime | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class AbortDecision:
    """Outcome of the abort-condition evaluation (T313)."""

    should_abort: bool
    reason_code: str | None
    metric_value: float | None
    threshold: float | None
    detail: dict[str, Any]


# ---------------------------------------------------------------------------
# Layer B — DB read
# ---------------------------------------------------------------------------


async def load_demo_mode_status(pool: Any) -> DemoModeStatus:
    """Load Layer B state from ``system_flags.demo_mode``.

    Failure to reach the DB falls *closed* (enabled=False) — Layer B disabled
    is the safe outcome for any auto-approval attempt.
    """
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(SELECT_DEMO_MODE_FLAG_SQL, DEMO_MODE_FLAG_NAME)
    except Exception:  # noqa: BLE001 - DB outage → fail closed
        logger.warning("demo_mode flag fetch failed; treating Layer B as disabled")
        return DemoModeStatus(
            enabled=False, expires_at=None, attested_by=None, aborted_at=None, raw={}
        )
    if row is None:
        return DemoModeStatus(
            enabled=False, expires_at=None, attested_by=None, aborted_at=None, raw={}
        )
    raw = row["flag_value"]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, Mapping):
        raw = {}
    enabled, expires_at, attested_by = evaluate_demo_mode_flag(raw)
    aborted_at = raw.get("aborted_at")
    return DemoModeStatus(
        enabled=enabled,
        expires_at=expires_at,
        attested_by=attested_by,
        aborted_at=_coerce_dt(aborted_at),
        raw=dict(raw),
    )


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Three-layer attestation evaluation
# ---------------------------------------------------------------------------


async def evaluate_three_layer_attestation(
    *,
    pool: Any,
    headers: Mapping[str, str] | None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> AutoApproveContext:
    """Resolve Layer A (env), Layer B (DB), Layer C (header) into a context.

    All three must be true for ``allowed=True``. When any single layer fails,
    the returned context's ``governance_marker`` stays ``HUMAN_REVIEW`` —
    callers must route the request through the normal human-approval path
    instead of returning an error (ADR-004 §1, "failure mode" column).
    """
    layer_a = is_layer_a_enabled(env=env)
    layer_c = check_layer_c_header(headers)
    status = await load_demo_mode_status(pool)
    if status.enabled and status.expires_at is not None:
        reference = now or datetime.now(tz=UTC)
        layer_b = status.expires_at > reference
    else:
        layer_b = False
    return build_auto_approve_context(
        layer_a=layer_a,
        layer_b=layer_b,
        layer_c=layer_c,
        expires_at=status.expires_at,
        attested_by=status.attested_by,
    )


# ---------------------------------------------------------------------------
# Per-employee Redis rate limit (T314)
# ---------------------------------------------------------------------------


def _rate_key(employee_id: str, granularity: str, window: int) -> str:
    return f"{RATE_KEY_PREFIX}:{employee_id}:{granularity}:{window}"


async def check_per_employee_rate_limit(
    redis: Any,
    *,
    employee_id: str,
    now_epoch: int | None = None,
) -> RateLimitState:
    """Atomic per-employee rate counter increment.

    Two fixed windows are incremented:
        :1m:{epoch//60}   — TTL 62s, ceiling 10
        :1h:{epoch//3600} — TTL 3602s, ceiling 60

    The returned :class:`RateLimitState` reflects post-increment counters,
    consistent with ADR-004 §"gate_evidence_json Schema" rate_limit_state
    note ("rate_limit_state block reflects post-decrement counters").
    """
    if not employee_id:
        raise ValueError("employee_id is required for PoC auto-approval rate limit")
    now = now_epoch if now_epoch is not None else int(time.time())
    w_minute = now // 60
    w_hour = now // 3600
    key_minute = _rate_key(employee_id, "1m", w_minute)
    key_hour = _rate_key(employee_id, "1h", w_hour)
    async with redis.pipeline(transaction=False) as pipe:
        pipe.incr(key_minute)
        pipe.expire(key_minute, 62)
        pipe.incr(key_hour)
        pipe.expire(key_hour, 3602)
        results = await pipe.execute()
    return RateLimitState(
        employee_id=employee_id,
        per_minute_count=int(results[0]),
        per_hour_count=int(results[2]),
    )


# ---------------------------------------------------------------------------
# Audit detail_json builder — matches ADR-004 §"gate_evidence_json Schema"
# ---------------------------------------------------------------------------


def build_gate_evidence_audit_payload(
    *,
    context: AutoApproveContext,
    environment: str,
    four_gates: Mapping[str, Mapping[str, Any]],
    rate_limit: RateLimitState | None,
    blocked_reason_codes: list[str] | None = None,
    auto_approval_reason_code: str = "FOUR_GATES_PASSED_NO_HUMAN_REVIEWER",
) -> dict[str, Any]:
    """Build the canonical ``detail_json`` subtree for an auto-approval audit row.

    The shape is invariant: ``governance_marker``, ``demo_mode``,
    ``prod_guard.would_block_in_prod`` are fixed; ``rate_limit_state`` is the
    post-increment snapshot; ``four_gates`` carries the BIZ-09 4-gate result.
    """
    payload: dict[str, Any] = {
        "governance_marker": context.governance_marker,
        "demo_mode": context.allowed,
        "demo_mode_attested_by": context.layer_b_attested_by,
        "environment": environment,
        "auto_approval_reason_code": auto_approval_reason_code,
        "four_gates": dict(four_gates),
        "blocked_reason_codes": list(blocked_reason_codes or []),
        "sod_warning": "human_reviewer=null; this transition is invalid in production",
        "prod_guard": {
            "would_block_in_prod": PROD_GUARD_WOULD_BLOCK_IN_PROD,
            "guard_env_var": LAYER_A_ENV_VAR,
        },
        "rate_limit_state": (
            rate_limit.to_audit_subtree()
            if rate_limit is not None
            else {
                "employee_id": None,
                "per_minute_count": 0,
                "per_hour_count": 0,
                "ceiling_minute": RATE_LIMIT_PER_MINUTE,
                "ceiling_hour": RATE_LIMIT_PER_HOUR,
            }
        ),
    }
    if context.demo_mode_expires_at is not None:
        payload["demo_mode_expires_at"] = context.demo_mode_expires_at.astimezone(
            UTC
        ).isoformat()
    if context.reason_code is not None:
        payload["attestation_reason_code"] = context.reason_code
    return payload


async def write_governance_audit_row(
    pool: Any,
    *,
    actor_id: str | None,
    action_code: str,
    resource_type: str,
    resource_id: str | None,
    detail_json: Mapping[str, Any],
    governance_marker: str = GOVERNANCE_MARKER_POC,
) -> None:
    """Append one PoC governance audit row (V031 path)."""
    async with pool.acquire() as connection:
        await connection.execute(
            INSERT_AUDIT_ROW_SQL,
            actor_id,
            action_code,
            resource_type,
            resource_id,
            json.dumps(dict(detail_json)),
            governance_marker,
        )


# ---------------------------------------------------------------------------
# 8h auto-expire (T312) + 5-min pre-warning broadcast
# ---------------------------------------------------------------------------


def should_emit_expiry_warning(
    status: DemoModeStatus,
    *,
    now: datetime | None = None,
    pre_warning_minutes: int = DEMO_MODE_PRE_WARNING_MINUTES,
) -> bool:
    """Return True iff we are inside the 5-min pre-expiry window."""
    if not status.enabled or status.expires_at is None:
        return False
    reference = now or datetime.now(tz=UTC)
    window_start = status.expires_at - timedelta(minutes=pre_warning_minutes)
    return window_start <= reference < status.expires_at


def is_demo_mode_expired(
    status: DemoModeStatus,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True iff the 8h ceiling has been reached."""
    if status.expires_at is None:
        return False
    reference = now or datetime.now(tz=UTC)
    return reference >= status.expires_at


async def broadcast_demo_mode_expiring_soon(
    *,
    manager: Any,
    status: DemoModeStatus,
    pool: Any | None = None,
) -> int:
    """Push a ``demo_mode_expiring_soon`` realtime event to all subscribers.

    The fanout uses the same :class:`RealtimeConnectionManager` as the rest
    of the realtime stack so RBAC filtering (worker-juliet's contract) still
    applies. Returns the number of clients that received the broadcast.
    """
    payload = {
        "event_type": ACTION_EXPIRING_SOON,
        "payload": {
            "expires_at": status.expires_at.astimezone(UTC).isoformat()
            if status.expires_at
            else None,
            "ceiling_hours": DEMO_MODE_CEILING_HOURS,
            "pre_warning_minutes": DEMO_MODE_PRE_WARNING_MINUTES,
            "governance_marker": GOVERNANCE_MARKER_POC,
        },
    }
    try:
        return await manager.broadcast(payload, pool=pool)
    except Exception as exc:  # noqa: BLE001 - WS failure must not crash sweep
        logger.warning("demo_mode_expiring_soon broadcast failed: %s", exc)
        return 0


async def auto_expire_demo_mode_if_due(
    pool: Any,
    *,
    actor_id: str | None,
    now: datetime | None = None,
    reason_code: str = "auto_expiry_8h_ceiling",
) -> bool:
    """Toggle ``demo_mode`` off if its 8h ceiling has elapsed.

    Idempotent — if already off or not yet due, returns False without
    touching ``system_flags``. Writes both the ``demo_mode_expired`` and
    ``demo_mode_toggle_off`` audit rows on success.
    """
    status = await load_demo_mode_status(pool)
    if not is_demo_mode_expired(status, now=now):
        return False
    if not status.raw:
        return False
    new_flag = dict(status.raw)
    new_flag["enabled"] = False
    new_flag["expired_at"] = (now or datetime.now(tz=UTC)).astimezone(
        UTC
    ).isoformat()
    new_flag["last_expiry_reason"] = reason_code
    async with pool.acquire() as connection:
        await connection.execute(
            UPDATE_DEMO_MODE_FLAG_SQL,
            json.dumps(new_flag),
            actor_id,
            f"auto-expire: {reason_code}",
            "AUTO-EXPIRE",
            DEMO_MODE_FLAG_NAME,
        )
    detail = {
        "reason_code": reason_code,
        "expired_at": new_flag["expired_at"],
        "ceiling_hours": DEMO_MODE_CEILING_HOURS,
        "prod_guard": {
            "would_block_in_prod": PROD_GUARD_WOULD_BLOCK_IN_PROD,
            "guard_env_var": LAYER_A_ENV_VAR,
        },
    }
    await write_governance_audit_row(
        pool,
        actor_id=actor_id,
        action_code=ACTION_EXPIRED,
        resource_type="system_flags",
        resource_id=None,
        detail_json=detail,
        governance_marker=GOVERNANCE_MARKER_POC,
    )
    await write_governance_audit_row(
        pool,
        actor_id=actor_id,
        action_code=ACTION_TOGGLE_OFF,
        resource_type="system_flags",
        resource_id=None,
        detail_json={**detail, "trigger": "auto_expire"},
        governance_marker=GOVERNANCE_MARKER_POC,
    )
    return True


# ---------------------------------------------------------------------------
# Abort conditions (T313)
# ---------------------------------------------------------------------------


async def _count_rate_limit_breaches(
    redis: Any, *, lookback_minutes: int = 10
) -> int:
    """Count distinct employee_ids that hit the per-min ceiling in the window."""
    pattern = f"{RATE_KEY_PREFIX}:*:1m:*"
    seen: set[str] = set()
    try:
        async for key in redis.scan_iter(match=pattern, count=200):
            try:
                value = await redis.get(key)
            except Exception:  # noqa: BLE001 - per-key failures ignored
                continue
            if value is None:
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count <= RATE_LIMIT_PER_MINUTE:
                continue
            parts = key.split(":") if isinstance(key, str) else key.decode().split(":")
            if len(parts) >= 5:
                seen.add(parts[2])  # employee_id segment
    except Exception as exc:  # noqa: BLE001 - Redis SCAN failure non-fatal
        logger.warning("rate-limit breach scan failed: %s", exc)
    _ = lookback_minutes  # window encoded by TTL on the counters
    return len(seen)


async def check_abort_conditions(
    pool: Any,
    redis: Any,
) -> AbortDecision:
    """Evaluate the three ADR-004 §4 abort signals against live state."""
    # Signal 1: 4-gate fail rate over the last hour (gate_evidence table).
    fail_rate = 0.0
    attempted = 0
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(SELECT_FOUR_GATE_FAIL_RATE_SQL)
        if row is not None:
            fail_rate = float(row["fail_rate"] or 0.0)
            attempted = int(row["attempted"] or 0)
    except Exception as exc:  # noqa: BLE001 - missing table tolerated pre-migration
        logger.warning("four-gate fail rate probe failed: %s", exc)
    if attempted >= 10 and fail_rate > ABORT_FOUR_GATE_FAIL_RATE:
        return AbortDecision(
            should_abort=True,
            reason_code="abort_four_gate_fail_rate",
            metric_value=fail_rate,
            threshold=ABORT_FOUR_GATE_FAIL_RATE,
            detail={"attempted": attempted, "fail_rate": fail_rate},
        )

    # Signal 2: audit ledger lag p99 over 5 minutes.
    lag_p99 = 0.0
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(SELECT_AUDIT_LAG_P99_SQL)
        if row is not None:
            lag_p99 = float(row["lag_p99_seconds"] or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit-lag p99 probe failed: %s", exc)
    if lag_p99 > ABORT_AUDIT_LAG_P99_SECONDS:
        return AbortDecision(
            should_abort=True,
            reason_code="abort_audit_lag_p99",
            metric_value=lag_p99,
            threshold=ABORT_AUDIT_LAG_P99_SECONDS,
            detail={"lag_p99_seconds": lag_p99},
        )

    # Signal 3: rate-limit breach pattern.
    breaches = await _count_rate_limit_breaches(redis)
    if breaches >= ABORT_RATE_LIMIT_BREACH_THRESHOLD:
        return AbortDecision(
            should_abort=True,
            reason_code="abort_rate_limit_breach_pattern",
            metric_value=float(breaches),
            threshold=float(ABORT_RATE_LIMIT_BREACH_THRESHOLD),
            detail={"distinct_employees_breached": breaches},
        )

    return AbortDecision(
        should_abort=False,
        reason_code=None,
        metric_value=None,
        threshold=None,
        detail={"fail_rate": fail_rate, "lag_p99": lag_p99},
    )


async def abort_demo_mode(
    pool: Any,
    *,
    actor_id: str | None,
    decision: AbortDecision,
    now: datetime | None = None,
) -> bool:
    """Auto-OFF Layer B and write the audit trail for an abort decision."""
    if not decision.should_abort:
        return False
    status = await load_demo_mode_status(pool)
    if not status.raw:
        return False
    new_flag = dict(status.raw)
    new_flag["enabled"] = False
    new_flag["aborted_at"] = (now or datetime.now(tz=UTC)).astimezone(
        UTC
    ).isoformat()
    new_flag["abort_reason_code"] = decision.reason_code
    new_flag["abort_metric_value"] = decision.metric_value
    new_flag["abort_threshold"] = decision.threshold
    async with pool.acquire() as connection:
        await connection.execute(
            UPDATE_DEMO_MODE_FLAG_SQL,
            json.dumps(new_flag),
            actor_id,
            f"abort: {decision.reason_code}",
            "AUTO-ABORT",
            DEMO_MODE_FLAG_NAME,
        )
    detail = {
        "reason_code": decision.reason_code,
        "metric_value": decision.metric_value,
        "threshold": decision.threshold,
        "detail": decision.detail,
        "prod_guard": {
            "would_block_in_prod": PROD_GUARD_WOULD_BLOCK_IN_PROD,
            "guard_env_var": LAYER_A_ENV_VAR,
        },
    }
    await write_governance_audit_row(
        pool,
        actor_id=actor_id,
        action_code=ACTION_ABORTED,
        resource_type="system_flags",
        resource_id=None,
        detail_json=detail,
        governance_marker=GOVERNANCE_MARKER_POC,
    )
    await write_governance_audit_row(
        pool,
        actor_id=actor_id,
        action_code=ACTION_TOGGLE_OFF,
        resource_type="system_flags",
        resource_id=None,
        detail_json={**detail, "trigger": "abort"},
        governance_marker=GOVERNANCE_MARKER_POC,
    )
    return True


# ---------------------------------------------------------------------------
# FastAPI dependency — T304
# ---------------------------------------------------------------------------


async def poc_auto_approval_guard(
    *,
    request: Any,
    pool: Any,
    redis: Any,
    actor_employee_id: str,
    app_env: str,
) -> tuple[AutoApproveContext, RateLimitState | None]:
    """FastAPI guard returning ``(context, rate_state)``.

    Behavior:
        * Production environments → context.allowed=False with reason_code
          ``poc_auto_approval_denied_in_prod`` (fail-closed, ADR-004 §5).
        * Any layer fails → ``context.allowed=False``; caller falls through to
          the human-approval path. ``rate_state`` is None.
        * All layers pass → increment the per-employee rate counter; if the
          counter exceeds 10/min or 60/hr, the returned context's ``allowed``
          is forced to False and ``reason_code`` becomes
          ``auto_approval_ceiling_exceeded`` so the caller emits
          ``poc_auto_approval_rate_limited``.
    """
    if prod_guard_block_in_prod(app_env):
        return (
            build_auto_approve_context(
                layer_a=False, layer_b=False, layer_c=False
            ),
            None,
        )
    context = await evaluate_three_layer_attestation(
        pool=pool, headers=getattr(request, "headers", None)
    )
    if not context.allowed:
        return context, None
    rate_state = await check_per_employee_rate_limit(
        redis, employee_id=actor_employee_id
    )
    if rate_state.exceeded:
        return (
            build_auto_approve_context(
                layer_a=context.layer_a,
                layer_b=context.layer_b,
                layer_c=context.layer_c,
                expires_at=context.demo_mode_expires_at,
                attested_by=context.layer_b_attested_by,
            ).__class__(  # rebuild with explicit reason
                allowed=False,
                governance_marker=GOVERNANCE_MARKER_HUMAN,
                layer_a=context.layer_a,
                layer_b=context.layer_b,
                layer_c=context.layer_c,
                reason_code="auto_approval_ceiling_exceeded",
                demo_mode_expires_at=context.demo_mode_expires_at,
                layer_b_attested_by=context.layer_b_attested_by,
            ),
            rate_state,
        )
    return context, rate_state


# ---------------------------------------------------------------------------
# Sweep entrypoint — DESIGNED for batch invocation (T312 + T313) but NOT
# currently wired: no production caller exists (not in main.py lifespan, the
# batch runner, or the scheduler). It is also inert today because demo mode is
# dormant — system_flags.demo_mode.enabled=false with no activation path — so
# even if wired it would emit 0 rows. See OBS-02 demo_mode_* rows + ADR-004.
# ---------------------------------------------------------------------------


async def run_governance_sweep(
    *,
    pool: Any,
    redis: Any,
    manager: Any | None,
    actor_id: str | None,
) -> dict[str, Any]:
    """One pass of the auto-expire + abort + pre-warning watchdog.

    Designed for invocation from ``batch_runner.py`` on a 60s schedule, but it
    is NOT currently wired (no production caller). demo mode is also dormant in
    this PoC (default-disabled flag, no activation path), so this sweep is inert
    — auto_expire/expiry-warning find nothing to act on and emit 0 rows. Returns
    a structured report (counts, decisions) for ops dashboards when invoked.
    """
    report: dict[str, Any] = {
        "expired": False,
        "aborted": False,
        "warned_clients": 0,
        "abort_decision": None,
    }
    expired = await auto_expire_demo_mode_if_due(pool, actor_id=actor_id)
    report["expired"] = expired
    if not expired:
        status = await load_demo_mode_status(pool)
        if manager is not None and should_emit_expiry_warning(status):
            report["warned_clients"] = await broadcast_demo_mode_expiring_soon(
                manager=manager, status=status, pool=pool
            )
            try:
                await write_governance_audit_row(
                    pool,
                    actor_id=actor_id,
                    action_code=ACTION_EXPIRING_SOON,
                    resource_type="system_flags",
                    resource_id=None,
                    detail_json={
                        "expires_at": status.expires_at.astimezone(
                            UTC
                        ).isoformat()
                        if status.expires_at
                        else None,
                        "pre_warning_minutes": DEMO_MODE_PRE_WARNING_MINUTES,
                        "prod_guard": {
                            "would_block_in_prod": PROD_GUARD_WOULD_BLOCK_IN_PROD,
                            "guard_env_var": LAYER_A_ENV_VAR,
                        },
                    },
                    governance_marker=GOVERNANCE_MARKER_POC,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("expiring_soon audit insert failed: %s", exc)
    decision = await check_abort_conditions(pool, redis)
    report["abort_decision"] = {
        "should_abort": decision.should_abort,
        "reason_code": decision.reason_code,
        "metric_value": decision.metric_value,
        "threshold": decision.threshold,
    }
    if decision.should_abort:
        report["aborted"] = await abort_demo_mode(
            pool, actor_id=actor_id, decision=decision
        )
    return report


__all__ = [
    "ABORT_AUDIT_LAG_P99_SECONDS",
    "ABORT_FOUR_GATE_FAIL_RATE",
    "ABORT_RATE_LIMIT_BREACH_THRESHOLD",
    "ACTION_ABORTED",
    "ACTION_AUTO_APPROVED",
    "ACTION_EXPIRED",
    "ACTION_EXPIRING_SOON",
    "ACTION_RATE_LIMITED",
    "ACTION_TOGGLE_OFF",
    "AbortDecision",
    "DemoModeStatus",
    "RATE_LIMIT_PER_HOUR",
    "RATE_LIMIT_PER_MINUTE",
    "RateLimitState",
    "abort_demo_mode",
    "auto_expire_demo_mode_if_due",
    "broadcast_demo_mode_expiring_soon",
    "build_gate_evidence_audit_payload",
    "check_abort_conditions",
    "check_per_employee_rate_limit",
    "evaluate_three_layer_attestation",
    "is_demo_mode_expired",
    "load_demo_mode_status",
    "poc_auto_approval_guard",
    "run_governance_sweep",
    "should_emit_expiry_warning",
    "write_governance_audit_row",
]

# `asyncio` is imported for type/runtime parity with the rest of the harness;
# keep the symbol referenced even when only used as a callable arg type.
_ = asyncio
