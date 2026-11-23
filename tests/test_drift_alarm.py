"""Stage 4 T245 — portfolio drift alarm classifier."""

from __future__ import annotations

import pytest

from apps.api.harness.services.portfolio.drift_alarm import (
    DEFAULT_AGGREGATE_ALARM_PP,
    DEFAULT_PER_CLASS_ALARM_PP,
    DEFAULT_PER_CLASS_WARN_PP,
    REQUIRED_CLASSES,
    classify_drift,
    compute_drift,
    evaluate,
)


def test_required_classes():
    assert REQUIRED_CLASSES == ("equity", "bond", "alt", "cash")


def test_default_thresholds():
    assert DEFAULT_PER_CLASS_WARN_PP == 5.0
    assert DEFAULT_PER_CLASS_ALARM_PP == 10.0
    assert DEFAULT_AGGREGATE_ALARM_PP == 15.0


def test_compute_drift_zero_when_identical():
    alloc = {"equity": 40, "bond": 40, "alt": 10, "cash": 10}
    d = compute_drift(alloc, alloc)
    assert d["max_abs_pp"] == 0
    assert d["aggregate_pp"] == 0
    assert all(v == 0 for v in d["per_class_abs_pp"].values())


def test_compute_drift_signed_and_abs():
    current = {"equity": 50, "bond": 30, "alt": 10, "cash": 10}
    target = {"equity": 40, "bond": 40, "alt": 10, "cash": 10}
    d = compute_drift(current, target)
    assert d["per_class_pp"] == {"equity": 10, "bond": -10, "alt": 0, "cash": 0}
    assert d["max_abs_pp"] == 10
    assert d["aggregate_pp"] == 10  # (10 + 10 + 0 + 0) / 2


def test_compute_drift_rejects_bad_sum():
    with pytest.raises(ValueError):
        compute_drift(
            {"equity": 50, "bond": 30, "alt": 10, "cash": 5},  # sums to 95
            {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
        )


def test_compute_drift_rejects_missing_class():
    with pytest.raises(ValueError):
        compute_drift(
            {"equity": 50, "bond": 30, "alt": 20},  # cash missing
            {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
        )


def test_compute_drift_rejects_extra_class():
    with pytest.raises(ValueError):
        compute_drift(
            {"equity": 40, "bond": 40, "alt": 10, "cash": 10, "crypto": 0},
            {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
        )


def test_compute_drift_rejects_out_of_range():
    with pytest.raises(ValueError):
        compute_drift(
            {"equity": -1, "bond": 41, "alt": 30, "cash": 30},
            {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
        )


def test_classify_normal():
    drift = compute_drift(
        {"equity": 42, "bond": 39, "alt": 10, "cash": 9},  # ≤2pp each
        {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    verdict = classify_drift(drift)
    assert verdict["severity"] == "NORMAL"
    assert verdict["triggers"] == []
    assert verdict["audit_action_code"] == ""


def test_classify_warn():
    drift = compute_drift(
        {"equity": 45, "bond": 35, "alt": 10, "cash": 10},  # 5pp on equity/bond
        {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    verdict = classify_drift(drift)
    assert verdict["severity"] == "WARN"
    assert verdict["audit_action_code"] == "portfolio_drift_warn"


def test_classify_alarm_per_class():
    drift = compute_drift(
        {"equity": 50, "bond": 30, "alt": 10, "cash": 10},  # 10pp on equity/bond
        {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    verdict = classify_drift(drift)
    assert verdict["severity"] == "ALARM"
    assert verdict["audit_action_code"] == "portfolio_drift_alarm_triggered"


def test_classify_alarm_aggregate():
    # Per-class only 8pp each (< 10pp alarm) but aggregate Σ|Δ|/2 = 16 ≥ 15
    drift = compute_drift(
        {"equity": 48, "bond": 32, "alt": 18, "cash": 2},
        {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    verdict = classify_drift(drift)
    assert verdict["severity"] == "ALARM"
    assert any("aggregate" in t for t in verdict["triggers"])


def test_classify_custom_thresholds():
    drift = compute_drift(
        {"equity": 41, "bond": 39, "alt": 10, "cash": 10},  # 1pp
        {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    # With tight thresholds, even 1pp triggers WARN
    verdict = classify_drift(drift, per_class_warn_pp=0.5, per_class_alarm_pp=2.0)
    assert verdict["severity"] == "WARN"


def test_evaluate_full_record():
    rec = evaluate(
        customer_id="cust-1",
        current={"equity": 50, "bond": 30, "alt": 10, "cash": 10},
        target={"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    assert rec["customer_id"] == "cust-1"
    assert rec["verdict"]["severity"] == "ALARM"
    assert rec["drift"]["max_abs_pp"] == 10


def test_evaluate_rejects_missing_customer_id():
    with pytest.raises(ValueError):
        evaluate(
            customer_id="",
            current={"equity": 40, "bond": 40, "alt": 10, "cash": 10},
            target={"equity": 40, "bond": 40, "alt": 10, "cash": 10},
        )


def test_compute_drift_deterministic():
    current = {"equity": 50, "bond": 30, "alt": 10, "cash": 10}
    target = {"equity": 40, "bond": 40, "alt": 10, "cash": 10}
    runs = set()
    for _ in range(50):
        d = compute_drift(current, target)
        runs.add((d["max_abs_pp"], d["aggregate_pp"]))
    assert len(runs) == 1


def test_sum_tolerance_accepts_99_99():
    # Allocation summing to 99.99 should pass (within ALLOCATION_SUM_TOLERANCE=0.01)
    d = compute_drift(
        {"equity": 39.99, "bond": 40, "alt": 10, "cash": 10},
        {"equity": 40, "bond": 40, "alt": 10, "cash": 10},
    )
    assert d["per_class_abs_pp"]["equity"] < 0.05
