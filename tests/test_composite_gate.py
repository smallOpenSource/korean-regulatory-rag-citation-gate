"""Composite gate tests (AC17 + S4 OR-leak block).

AC mapping: AC1/AC2/AC3/AC4 (composite states), AC17 (3-script split), S4 (OR-leak block).

4 cases:
    Case 1: STATIC=PASS, RUNTIME=PASS  → composite PASS
    Case 2: STATIC=PASS, RUNTIME=STALE → composite FAIL
    Case 3: STATIC=PASS, denominator=0 → composite FAIL
    Case 4: STATIC=FAIL                → composite FAIL

All cases use mock JSON inputs (no live DB required).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure scripts/ is importable
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _offset_z(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_static_result(tmp_path: Path, *, passed: bool) -> Path:
    """Write a minimal static result JSON and return its path."""
    data = {
        "verified_at": _now_z(),
        "status": "passed" if passed else "failed",
        "passed": passed,
        "evidence_paths": [],
        "principles": {},
    }
    fpath = tmp_path / "static_result.json"
    fpath.write_text(json.dumps(data), encoding="utf-8")
    return fpath


def _write_runtime_measurement(
    mdir: Path,
    principle: str,
    metric: str,
    *,
    denominator: int,
    expired: bool = False,
) -> None:
    """Write a runtime measurement JSON into mdir."""
    now = datetime.now(UTC)
    if expired:
        last_measured = now - timedelta(days=8)
        expires_at = now - timedelta(days=1)
    else:
        last_measured = now
        expires_at = now + timedelta(days=7)

    data = {
        "principle_id": principle,
        "metric": metric,
        "value": 0.95,
        "p95": None,
        "sample_n": max(denominator, 0),
        "denominator_source": "audit_logs.AI_CALL_STARTED",
        "denominator": denominator,
        "last_measured_at": last_measured.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_path": f"docs/ai/measurements/{principle}_{metric}.json",
    }
    fpath = mdir / f"{principle}_{metric}.json"
    fpath.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Import under test (patch MEASUREMENTS_DIR per test via monkeypatch)
# ---------------------------------------------------------------------------

import verify_total_product_readiness as vtpr


# ---------------------------------------------------------------------------
# Case 1: STATIC=PASS, RUNTIME=PASS → composite PASS
# ---------------------------------------------------------------------------

def test_composite_pass_when_static_and_runtime_pass(tmp_path, monkeypatch):
    """AC1: STATIC=PASS AND RUNTIME=PASS → composite_passed=True."""
    mdir = tmp_path / "measurements"
    mdir.mkdir()
    _write_runtime_measurement(mdir, "P1_safety", "fail_closed_rate", denominator=100)

    monkeypatch.setattr(vtpr, "MEASUREMENTS_DIR", mdir)

    static_path = _write_static_result(tmp_path, passed=True)
    result = vtpr.validate_composite_gate(static_result_path=static_path)

    assert result.passed is True, f"Expected PASS, errors: {result.errors}"
    assert result.detail is not None
    assert result.detail["composite_passed"] is True
    assert result.detail["static_passed"] is True
    assert result.detail["runtime_passed"] is True
    assert result.detail["denominator"] >= 1


# ---------------------------------------------------------------------------
# Case 2: STATIC=PASS, RUNTIME=STALE → composite FAIL
# ---------------------------------------------------------------------------

def test_composite_fail_when_runtime_stale(tmp_path, monkeypatch):
    """AC2: STATIC=PASS but RUNTIME expired → composite_passed=False (S4 OR-leak blocked)."""
    mdir = tmp_path / "measurements"
    mdir.mkdir()
    _write_runtime_measurement(
        mdir, "P1_safety", "fail_closed_rate", denominator=100, expired=True
    )

    monkeypatch.setattr(vtpr, "MEASUREMENTS_DIR", mdir)

    static_path = _write_static_result(tmp_path, passed=True)
    result = vtpr.validate_composite_gate(static_result_path=static_path)

    assert result.passed is False, "Expected FAIL when runtime is stale"
    assert result.detail is not None
    assert result.detail["composite_passed"] is False
    # At least one staleness-related error must be present
    assert any(
        "stale" in e.lower() or "freshness" in e.lower() or "runtime" in e.lower()
        for e in result.errors
    ), f"Expected staleness error in: {result.errors}"


# ---------------------------------------------------------------------------
# Case 3: STATIC=PASS, denominator=0 → composite FAIL
# ---------------------------------------------------------------------------

def test_composite_fail_when_denominator_zero(tmp_path, monkeypatch):
    """AC3: STATIC=PASS but denominator=0 → composite_passed=False (NR1+NR7 fix enforced)."""
    mdir = tmp_path / "measurements"
    mdir.mkdir()
    _write_runtime_measurement(
        mdir, "P1_safety", "fail_closed_rate", denominator=0
    )

    monkeypatch.setattr(vtpr, "MEASUREMENTS_DIR", mdir)

    static_path = _write_static_result(tmp_path, passed=True)
    result = vtpr.validate_composite_gate(static_result_path=static_path)

    assert result.passed is False, "Expected FAIL when denominator=0"
    assert result.detail is not None
    assert result.detail["composite_passed"] is False
    assert result.detail["denominator"] == 0
    assert any(
        "denominator" in e.lower() or "runtime" in e.lower()
        for e in result.errors
    ), f"Expected denominator error in: {result.errors}"


# ---------------------------------------------------------------------------
# Case 4: STATIC=FAIL → composite FAIL
# ---------------------------------------------------------------------------

def test_composite_fail_when_static_fails(tmp_path, monkeypatch):
    """AC4: STATIC=FAIL → composite_passed=False regardless of runtime state."""
    mdir = tmp_path / "measurements"
    mdir.mkdir()
    _write_runtime_measurement(mdir, "P1_safety", "fail_closed_rate", denominator=100)

    monkeypatch.setattr(vtpr, "MEASUREMENTS_DIR", mdir)

    static_path = _write_static_result(tmp_path, passed=False)
    result = vtpr.validate_composite_gate(static_result_path=static_path)

    assert result.passed is False, "Expected FAIL when static check fails"
    assert result.detail is not None
    assert result.detail["composite_passed"] is False
    assert result.detail["static_passed"] is False
    assert any(
        "static" in e.lower()
        for e in result.errors
    ), f"Expected static failure error in: {result.errors}"
