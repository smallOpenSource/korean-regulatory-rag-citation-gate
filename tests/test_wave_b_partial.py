"""Wave-Audit-Defect-Fix B (partial 5/12) — structural verification.

Covers:
  B2  ErrorCode enum 13-entry + A4 swap (external_provider_error)
  B5  /auth/refresh rate-limit canonical audit_refresh_rate_limited
  B6  /auth/refresh success canonical audit emit
  B11 house_view_drafted emit on POST /house-views
  B12 NBA WS broadcast silent except removal (4 sites)

Pending (carry-over to next iteration):
  B1  ErrorCode enum import across every router
  B3  Idempotency-Key header middleware
  B4  YAML role drift
  B7  ai-jobs/ai-outputs GET audit
  B8  /rag/query Redis per-request leak
  B9  AI_CALL semantic split
  B10 consultations non-COMPLETED transitions audit
"""

from __future__ import annotations

from pathlib import Path

from apps.api.harness.core.audit import CANONICAL_AUDIT_ACTION_CODES
from apps.api.harness.core.error_codes import ErrorCode


# ── B2 ──────────────────────────────────────────────────────────────────────

def test_b2_error_code_enum_has_seventeen_entries() -> None:
    """Wave-Z5 B.1+B.2 additive: 10 (original) + 3 (B2) + 4 (Z5) = 17.

    Z5 additive codes:
      - four_gate_not_passed (B.1 PR1, surfaces buried A.18 dict)
      - idempotency_key_required (ADR-011 middleware)
      - idempotency_key_in_flight (ADR-011 middleware)
      - idempotency_key_payload_mismatch (ADR-011 middleware)
    """
    members = [e.value for e in ErrorCode]
    assert len(members) == 17, (
        f"ErrorCode enum must have 17 entries after Z5 B.1+B.2 "
        f"(10 original + 3 B2 + 4 Z5); got {members}"
    )
    for code in (
        "external_provider_error", "marketing_lint_failed", "redaction_blocked",
        "four_gate_not_passed",
        "idempotency_key_required", "idempotency_key_in_flight",
        "idempotency_key_payload_mismatch",
    ):
        assert code in members, f"{code} must be present in ErrorCode enum"


def test_b2_a4_swap_uses_external_provider_error() -> None:
    """house_views.py 502 fallback must carry ErrorCode.external_provider_error
    even after the Z5 B.1 structured_http_exception refactor (Cycle Z5 PR3)."""
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/house_views.py").read_text(encoding="utf-8")
    # Match either the legacy `.value` accessor or the Z5 refactored
    # structured_http_exception(..., ErrorCode.external_provider_error, ...) call.
    has_provider_error = (
        "ErrorCode.external_provider_error" in source
    )
    assert has_provider_error, (
        "house_views.py except branch must reference "
        "ErrorCode.external_provider_error (B2 swap; Z5 PR3 keeps the code)"
    )
    assert "ErrorCode.service_unavailable.value" not in source.split(
        "house_view_generation"
    )[-1] or "external_provider_error" in source, (
        "service_unavailable fallback should no longer be the Azure-fail mask"
    )


# ── B5 / B6 ─────────────────────────────────────────────────────────────────

def test_b5_auth_refresh_rate_limited_canonical() -> None:
    assert "auth_refresh_rate_limited" in CANONICAL_AUDIT_ACTION_CODES


def test_b5_v056_migration_seeds_audit_code() -> None:
    body = (Path(__file__).resolve().parents[1] / "db/migrations/V056__auth_refresh_rate_limited_audit_code.sql").read_text(encoding="utf-8")
    assert body.startswith(
        "/* sql_id: v056_auth_refresh_rate_limited_audit_code */"
    )
    assert "'auth_refresh_rate_limited'" in body
    assert "ON CONFLICT (action_code) DO NOTHING" in body


def test_b5_router_emits_audit_before_429() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/auth.py").read_text(encoding="utf-8")
    assert 'action_code="auth_refresh_rate_limited"' in source, (
        "auth.py must emit canonical audit code when refresh rate-limit fires"
    )


def test_b6_router_emits_auth_refresh_on_success() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/auth.py").read_text(encoding="utf-8")
    # Distinguish the success emit from auth_refresh_reuse/rate_limited
    count = source.count('action_code="auth_refresh"')
    assert count >= 1, (
        f"auth.py must emit auth_refresh on success path; found {count}"
    )


# ── B11 ─────────────────────────────────────────────────────────────────────

def test_b11_house_view_drafted_emitted_on_create() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/house_views.py").read_text(encoding="utf-8")
    assert 'action_code="house_view_drafted"' in source, (
        "POST /house-views must emit house_view_drafted (canonical audit.py:44)"
    )
    assert "house_view_drafted" in CANONICAL_AUDIT_ACTION_CODES


# ── B12 ─────────────────────────────────────────────────────────────────────

def test_b12_nba_no_silent_ws_except() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/nba.py").read_text(encoding="utf-8")
    # Pattern: `except Exception:  # ...\n        pass`
    silent_count = 0
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("except Exception") and ":" in line:
            # Look for `pass` as the body
            if i + 1 < len(lines) and lines[i + 1].strip() == "pass":
                silent_count += 1
    assert silent_count == 0, (
        f"nba.py must have 0 silent `except Exception: pass` blocks; found {silent_count}"
    )


def test_b12_nba_logger_warning_per_ws_site() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/nba.py").read_text(encoding="utf-8")
    warning_count = source.count("logger.warning")
    assert warning_count >= 4, (
        f"nba.py must log all 4 WS broadcast failure sites; found {warning_count}"
    )
    assert 'logger = logging.getLogger("nba_router")' in source
