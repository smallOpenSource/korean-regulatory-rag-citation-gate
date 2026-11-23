"""Wave-Audit-Defect-Fix B (continued 5/12 → 10/12) — structural verification.

Covers:
  B7  /ai-jobs/{id} + /ai-outputs/{id} GET audit emit (V057 canonical)
  B8  /rag/query Redis per-request leak → request-scoped get_async_redis
  B9  AI_CALL_FAILED no-citation block → citation_gate_failed canonical split
  B10 consultations non-COMPLETED transitions → consultation_status_changed
  B12-followup nba_ws_broadcast_failed canonical (paired with B12 logger.warning)

V057 reserved slot for these 6 new canonical audit codes:
  ai_job_get / ai_output_get / citation_gate_failed / provider_failure /
  consultation_status_changed / nba_ws_broadcast_failed.

Still carry-over after this iteration:
  B1  ErrorCode enum import 전 router (large refactor)
  B3  Idempotency-Key header middleware
  B4  YAML role drift
"""

from __future__ import annotations

from pathlib import Path

from apps.api.harness.core.audit import CANONICAL_AUDIT_ACTION_CODES


# ── V057 + canonical ─────────────────────────────────────────────────────────

def test_v057_migration_present_with_six_codes() -> None:
    migration = (Path(__file__).resolve().parents[1] / "db/migrations/V057__wave_b_audit_action_codes.sql")
    assert migration.exists()
    body = migration.read_text(encoding="utf-8")
    assert body.startswith("/* sql_id: v057_wave_b_audit_action_codes */"), (
        "V057 first line must be canonical /* sql_id: ... */ "
        "per feedback-v-sql-sql-id-validator"
    )
    for code in (
        "ai_job_get",
        "ai_output_get",
        "citation_gate_failed",
        "provider_failure",
        "consultation_status_changed",
        "nba_ws_broadcast_failed",
    ):
        assert f"'{code}'" in body, f"V057 must seed {code}"
    assert "ON CONFLICT (action_code) DO NOTHING" in body, (
        "V057 must be idempotent re-run safe"
    )


def test_six_new_codes_canonical_in_python_tuple() -> None:
    for code in (
        "ai_job_get",
        "ai_output_get",
        "citation_gate_failed",
        "provider_failure",
        "consultation_status_changed",
        "nba_ws_broadcast_failed",
    ):
        assert code in CANONICAL_AUDIT_ACTION_CODES, (
            f"{code} must be in CANONICAL_AUDIT_ACTION_CODES; missing Python "
            "registration creates a silent DB ↔ canonical gap"
        )


# ── B7 ───────────────────────────────────────────────────────────────────────

def test_b7_ai_jobs_get_emits_audit() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/ai.py").read_text(encoding="utf-8")
    assert 'action_code="ai_job_get"' in source, (
        "/ai-jobs/{id} GET must emit ai_job_get audit row"
    )


def test_b7_ai_outputs_get_emits_audit() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/ai.py").read_text(encoding="utf-8")
    assert 'action_code="ai_output_get"' in source, (
        "/ai-outputs/{id} GET must emit ai_output_get audit row"
    )


# ── B8 ───────────────────────────────────────────────────────────────────────

def test_b8_rag_query_uses_request_scoped_redis() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/ai.py").read_text(encoding="utf-8")
    assert "_redis = get_async_redis(request)" in source, (
        "rag_query must use request-scoped Redis client from dependencies"
    )
    # Old per-request `from apps.api.harness.core.redis_client import create_redis_client`
    # inline-in-function import must be gone (its presence inside rag_query was the
    # symptom of the per-request socket leak).
    assert (
        "from apps.api.harness.core.redis_client import create_redis_client"
        not in source
    ), "inline create_redis_client import inside rag_query must be removed (B8 leak)"


# ── B9 ───────────────────────────────────────────────────────────────────────

def test_b9_citation_gate_failed_replaces_ai_call_failed_no_citation() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/ai.py").read_text(encoding="utf-8")
    assert 'action_code="citation_gate_failed"' in source, (
        "no-citation block must emit citation_gate_failed (not AI_CALL_FAILED umbrella)"
    )


# ── B10 ──────────────────────────────────────────────────────────────────────

def test_b10_consultation_status_changed_for_non_completed() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/consultations.py").read_text(encoding="utf-8")
    assert 'action_code="consultation_status_changed"' in source, (
        "non-COMPLETED status transitions must emit consultation_status_changed"
    )
    # Must compare existing vs updated to detect real transition
    assert 'existing.get("status_code") != updated.get("status_code")' in source, (
        "B10 branch must guard on actual status diff to avoid noisy emits"
    )


# ── OBS-02 doc rows ──────────────────────────────────────────────────────────

def test_obs02_documents_six_new_codes() -> None:
    body = (Path(__file__).resolve().parents[1] / "docs/observability/OBS-02_audit_action_codes.md").read_text(encoding="utf-8")
    for code in (
        "ai_job_get",
        "ai_output_get",
        "citation_gate_failed",
        "provider_failure",
        "consultation_status_changed",
        "nba_ws_broadcast_failed",
    ):
        assert f"| {code} |" in body, (
            f"OBS-02 must document {code} so audit reviewers know the meaning"
        )
