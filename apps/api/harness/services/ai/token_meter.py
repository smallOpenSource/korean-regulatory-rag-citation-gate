"""LLM10 per-employee token rate ceiling + monthly cap (ADR-005, REG-04 §3.7, W3-T6).

Per-employee ceilings (OWASP LLM10 — Unbounded Resource Consumption):
  • 50 000 tokens/min  → Redis key  harness:ai:tokens:{employee_id}:1m  TTL 60 s
  • 500 000 tokens/hr  → Redis key  harness:ai:tokens:{employee_id}:1h  TTL 3600 s

Monthly cumulative cap (REG-04 §3.7):
  • 560 000 tokens/month → Redis key  harness:ai:tokens:global:monthly
  • Abort signals at 70 % / 85 % / 100 %

On ceiling breach: caller emits HTTP 429 + ai_token_rate_limited audit row.
Fail-open when Redis is unavailable.
"""

from __future__ import annotations

import os
import time as time_module
from dataclasses import dataclass
from typing import Any

# ── Configuration (env-overridable) ──────────────────────────────────────────

PER_EMPLOYEE_CEILING_1M: int = int(os.getenv("AI_TOKEN_CEILING_PER_MIN", "50000"))
PER_EMPLOYEE_CEILING_1H: int = int(os.getenv("AI_TOKEN_CEILING_PER_HOUR", "500000"))
MONTHLY_CEILING: int = int(os.getenv("AI_TOKEN_CEILING_MONTHLY", "560000"))

_KEY_1M = "harness:ai:tokens:{employee_id}:1m"
_KEY_1H = "harness:ai:tokens:{employee_id}:1h"
_KEY_MONTHLY = "harness:ai:tokens:global:monthly"


@dataclass(frozen=True)
class TokenRateResult:
    """Result of one token-rate ceiling check."""

    exceeded: bool
    reason: str | None          # "per_minute" | "per_hour" | "monthly" | None
    employee_id: str
    tokens_consumed_1m: int
    tokens_consumed_1h: int
    tokens_consumed_monthly: int
    warning_level: str | None   # "warn_70" | "warn_85" | "abort_100" | None


def check_token_rate(
    employee_id: str,
    tokens_requested: int,
    redis_client: Any,
) -> TokenRateResult:
    """Check and increment per-employee + global monthly token counters.

    Uses Redis INCRBY + EXPIRE for sliding-window approximation.
    Fails open when *redis_client* is None or Redis is unreachable.

    Args:
        employee_id: Authenticated employee identifier.
        tokens_requested: Estimated total tokens for this request (in + out).
        redis_client: Synchronous redis.Redis instance, or None.

    Returns:
        TokenRateResult — inspect ``exceeded`` to return 429.
    """
    if redis_client is None:
        return _open_result(employee_id, tokens_requested)

    try:
        pipe = redis_client.pipeline(transaction=True)
        key_1m = _KEY_1M.format(employee_id=employee_id)
        key_1h = _KEY_1H.format(employee_id=employee_id)
        pipe.incrby(key_1m, tokens_requested)
        pipe.expire(key_1m, 60)
        pipe.incrby(key_1h, tokens_requested)
        pipe.expire(key_1h, 3600)
        pipe.incrby(_KEY_MONTHLY, tokens_requested)
        results = pipe.execute()
        val_1m = int(results[0] or 0)
        val_1h = int(results[2] or 0)
        val_monthly = int(results[4] or 0)
    except Exception:  # noqa: BLE001 — fail-open on Redis error
        return _open_result(employee_id, tokens_requested)

    if val_1m > PER_EMPLOYEE_CEILING_1M:
        return _exceeded("per_minute", employee_id, val_1m, val_1h, val_monthly)

    if val_1h > PER_EMPLOYEE_CEILING_1H:
        return _exceeded("per_hour", employee_id, val_1m, val_1h, val_monthly)

    monthly_ratio = val_monthly / MONTHLY_CEILING if MONTHLY_CEILING > 0 else 0.0
    if monthly_ratio >= 1.0:
        return _exceeded("monthly", employee_id, val_1m, val_1h, val_monthly)

    warning_level: str | None = None
    if monthly_ratio >= 0.85:
        warning_level = "warn_85"
    elif monthly_ratio >= 0.70:
        warning_level = "warn_70"

    return TokenRateResult(
        exceeded=False, reason=None, employee_id=employee_id,
        tokens_consumed_1m=val_1m, tokens_consumed_1h=val_1h,
        tokens_consumed_monthly=val_monthly, warning_level=warning_level,
    )


def record_azure_token_consumption(
    *,
    tokens_in: int,
    tokens_out: int,
    model: str,
    agent_id: str,
    cost_per_1m_in: float = 0.15,
    cost_per_1m_out: float = 0.60,
) -> dict[str, Any]:
    """Build token_consumption dict for audit_logs.detail_json (ADR-007 §3.7).

    Args:
        tokens_in: Prompt tokens used.
        tokens_out: Completion tokens used.
        model: Azure deployment name.
        agent_id: Calling agent identifier.
        cost_per_1m_in: USD per 1M input tokens (default GPT-4o-mini rate).
        cost_per_1m_out: USD per 1M output tokens.

    Returns:
        dict suitable for inclusion in audit_logs.detail_json['token_consumption'].
    """
    cost_usd_est = (
        tokens_in * cost_per_1m_in / 1_000_000
        + tokens_out * cost_per_1m_out / 1_000_000
    )
    return {
        "azure_tokens_in": tokens_in,
        "azure_tokens_out": tokens_out,
        "azure_cost_usd_est": round(cost_usd_est, 6),
        "model": model,
        "agent_id": agent_id,
        "recorded_at_unix": int(time_module.time()),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _open_result(employee_id: str, tokens_requested: int) -> TokenRateResult:
    """Fail-open result when Redis is unavailable."""
    return TokenRateResult(
        exceeded=False, reason=None, employee_id=employee_id,
        tokens_consumed_1m=tokens_requested,
        tokens_consumed_1h=tokens_requested,
        tokens_consumed_monthly=tokens_requested,
        warning_level=None,
    )


def _exceeded(
    reason: str, employee_id: str,
    val_1m: int, val_1h: int, val_monthly: int,
) -> TokenRateResult:
    return TokenRateResult(
        exceeded=True, reason=reason, employee_id=employee_id,
        tokens_consumed_1m=val_1m, tokens_consumed_1h=val_1h,
        tokens_consumed_monthly=val_monthly,
        warning_level="abort_100" if reason == "monthly" else None,
    )
