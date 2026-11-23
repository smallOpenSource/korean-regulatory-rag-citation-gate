"""Portfolio allocation drift alarm (T245).

Compares a customer's current asset-class allocation against the target
allocation declared by the active house-view (or a custom target) and
emits an alarm when the drift exceeds policy thresholds.

Drift metrics:
  - per-class absolute drift (percentage points)
  - max single-class deviation
  - aggregate L1 drift (Σ |current - target|) / 2 — bounded [0, 1] when
    expressed as a fraction (or [0, 100] when in percentage points)

Default policy thresholds (override per customer / segment / mandate):
  - per_class_pp_warn  = 5.0    pp deviation triggers WARN
  - per_class_pp_alarm = 10.0   pp deviation triggers ALARM
  - aggregate_pp_alarm = 15.0   total Σ|Δ|/2 (percentage points) → ALARM
"""

from __future__ import annotations

# Required asset classes per the canonical Customer 360 allocation pie.
REQUIRED_CLASSES: tuple[str, ...] = ("equity", "bond", "alt", "cash")

DEFAULT_PER_CLASS_WARN_PP: float = 5.0
DEFAULT_PER_CLASS_ALARM_PP: float = 10.0
DEFAULT_AGGREGATE_ALARM_PP: float = 15.0
ALLOCATION_SUM_TOLERANCE: float = 0.01  # 100 ± 0.01 pp acceptable


def _validate_allocation(label: str, alloc: dict[str, float]) -> None:
    if not isinstance(alloc, dict):
        raise TypeError(f"{label} must be a dict")
    missing = [c for c in REQUIRED_CLASSES if c not in alloc]
    if missing:
        raise ValueError(f"{label} missing classes: {missing}")
    extra = [k for k in alloc if k not in REQUIRED_CLASSES]
    if extra:
        raise ValueError(f"{label} has unsupported classes: {extra}")
    total = sum(float(alloc[c]) for c in REQUIRED_CLASSES)
    if abs(total - 100.0) > ALLOCATION_SUM_TOLERANCE:
        raise ValueError(f"{label} must sum to 100 pp (got {total:.2f})")
    for c in REQUIRED_CLASSES:
        v = float(alloc[c])
        if v < 0 or v > 100:
            raise ValueError(f"{label}.{c}={v} out of [0,100]")


def compute_drift(
    current: dict[str, float],
    target: dict[str, float],
) -> dict[str, object]:
    """Compute per-class drift + aggregate L1/2 between current and target.

    Returns:
        per_class_pp: dict[str, float] — current[c] - target[c] (signed pp)
        per_class_abs_pp: dict[str, float] — |current[c] - target[c]|
        max_abs_pp: float
        aggregate_pp: float — Σ|Δ|/2 expressed in percentage points
    """
    _validate_allocation("current", current)
    _validate_allocation("target", target)
    per_class_signed = {c: float(current[c]) - float(target[c]) for c in REQUIRED_CLASSES}
    per_class_abs = {c: abs(v) for c, v in per_class_signed.items()}
    max_abs = max(per_class_abs.values()) if per_class_abs else 0.0
    aggregate = sum(per_class_abs.values()) / 2.0
    return {
        "per_class_pp": per_class_signed,
        "per_class_abs_pp": per_class_abs,
        "max_abs_pp": max_abs,
        "aggregate_pp": aggregate,
    }


def classify_drift(
    drift: dict[str, object],
    *,
    per_class_warn_pp: float = DEFAULT_PER_CLASS_WARN_PP,
    per_class_alarm_pp: float = DEFAULT_PER_CLASS_ALARM_PP,
    aggregate_alarm_pp: float = DEFAULT_AGGREGATE_ALARM_PP,
) -> dict[str, object]:
    """Apply policy thresholds → severity NORMAL / WARN / ALARM.

    Returns:
        severity: 'NORMAL' | 'WARN' | 'ALARM'
        triggers: list[str] — explanation strings (each maps to one rule)
        audit_action_code: '' | 'portfolio_drift_warn' | 'portfolio_drift_alarm_triggered'
    """
    per_class_abs_raw = drift.get("per_class_abs_pp")
    max_abs_raw = drift.get("max_abs_pp")
    aggregate_raw = drift.get("aggregate_pp")
    if not isinstance(per_class_abs_raw, dict):
        raise TypeError("drift.per_class_abs_pp must be dict")
    per_class_abs: dict[str, float] = {str(k): float(v) for k, v in per_class_abs_raw.items()}
    max_abs = float(max_abs_raw) if isinstance(max_abs_raw, (int, float)) else 0.0
    aggregate = float(aggregate_raw) if isinstance(aggregate_raw, (int, float)) else 0.0

    triggers: list[str] = []
    severity = "NORMAL"

    if max_abs >= per_class_alarm_pp:
        offenders = [c for c, v in per_class_abs.items() if v >= per_class_alarm_pp]
        triggers.append(
            f"per-class drift ≥ {per_class_alarm_pp}pp on: {sorted(offenders)}"
        )
        severity = "ALARM"
    elif max_abs >= per_class_warn_pp:
        offenders = [c for c, v in per_class_abs.items() if v >= per_class_warn_pp]
        triggers.append(
            f"per-class drift ≥ {per_class_warn_pp}pp on: {sorted(offenders)}"
        )
        severity = "WARN"

    if aggregate >= aggregate_alarm_pp:
        triggers.append(f"aggregate drift ≥ {aggregate_alarm_pp}pp ({aggregate:.2f})")
        severity = "ALARM"

    if severity == "ALARM":
        code = "portfolio_drift_alarm_triggered"
    elif severity == "WARN":
        code = "portfolio_drift_warn"
    else:
        code = ""

    return {
        "severity": severity,
        "triggers": triggers,
        "audit_action_code": code,
        "thresholds": {
            "per_class_warn_pp": per_class_warn_pp,
            "per_class_alarm_pp": per_class_alarm_pp,
            "aggregate_alarm_pp": aggregate_alarm_pp,
        },
    }


def evaluate(
    *,
    customer_id: str,
    current: dict[str, float],
    target: dict[str, float],
    per_class_warn_pp: float = DEFAULT_PER_CLASS_WARN_PP,
    per_class_alarm_pp: float = DEFAULT_PER_CLASS_ALARM_PP,
    aggregate_alarm_pp: float = DEFAULT_AGGREGATE_ALARM_PP,
) -> dict[str, object]:
    """End-to-end drift evaluation for one customer; returns full record."""
    if not customer_id:
        raise ValueError("customer_id required")
    drift = compute_drift(current, target)
    verdict = classify_drift(
        drift,
        per_class_warn_pp=per_class_warn_pp,
        per_class_alarm_pp=per_class_alarm_pp,
        aggregate_alarm_pp=aggregate_alarm_pp,
    )
    return {
        "customer_id": customer_id,
        "current": current,
        "target": target,
        "drift": drift,
        "verdict": verdict,
    }
