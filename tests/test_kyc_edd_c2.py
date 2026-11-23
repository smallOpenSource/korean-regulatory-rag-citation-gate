"""Wave-Audit-Defect-Fix C2 — kyc_edd canonical split + KycEddPage 신규.

Plan §6 line 367 + OQ-1 + OQ-5:
  * routers/kyc_edd.py:184 /complete endpoint emit split from kyc_edd_reassessed
    to kyc_edd_completed (resolves OQ-1; before split it was indistinguishable
    from the /reassess endpoint's emit).
  * V060 migration registers 4 new canonical codes: kyc_edd_completed,
    kyc_edd_trigger_listed, kyc_edd_trigger_detail_viewed, kyc_edd_evaluated
    (resolves OQ-5).
  * Frontend page binds the 5 lifecycle endpoints (list/detail/evaluate/
    reassess/complete).
"""

from __future__ import annotations

from pathlib import Path

from apps.api.harness.api.routers import kyc_edd as kyc_edd_router
from apps.api.harness.core.audit import (
    CANONICAL_AUDIT_ACTION_CODES,
    is_valid_audit_action,
)


def test_v060_migration_present_with_four_codes() -> None:
    migration = (Path(__file__).resolve().parents[1] / "db/migrations/V060__kyc_edd_audit_action_codes.sql")
    assert migration.exists()
    body = migration.read_text(encoding="utf-8")
    assert body.startswith("/* sql_id: v060_kyc_edd_audit_action_codes */"), (
        "V060 first line must be canonical /* sql_id: ... */"
    )
    for code in (
        "kyc_edd_completed",
        "kyc_edd_trigger_listed",
        "kyc_edd_trigger_detail_viewed",
        "kyc_edd_evaluated",
    ):
        assert f"'{code}'" in body, f"V060 must seed {code}"
    assert "ON CONFLICT (action_code) DO NOTHING" in body


def test_four_kyc_edd_codes_canonical() -> None:
    for code in (
        "kyc_edd_completed",
        "kyc_edd_trigger_listed",
        "kyc_edd_trigger_detail_viewed",
        "kyc_edd_evaluated",
    ):
        assert code in CANONICAL_AUDIT_ACTION_CODES, (
            f"{code} must be in CANONICAL_AUDIT_ACTION_CODES"
        )
        assert is_valid_audit_action(code) is True


def test_complete_endpoint_emits_kyc_edd_completed_not_reassessed() -> None:
    source = Path(kyc_edd_router.__file__).read_text(encoding="utf-8")
    # The /complete endpoint must emit kyc_edd_completed
    assert 'action_code="kyc_edd_completed"' in source, (
        "OQ-1 — /kyc-edd/triggers/{id}/complete must emit kyc_edd_completed"
    )
    # The /reassess endpoint must still emit kyc_edd_reassessed (preserved)
    assert source.count('action_code="kyc_edd_reassessed"') == 1, (
        "exactly one kyc_edd_reassessed emit must remain (the reassess "
        "endpoint at line 152); the complete endpoint at line 184 was split"
    )
    # The legacy kyc_edd_triggered emit on POST /triggers must also remain
    assert 'action_code="kyc_edd_triggered"' in source


def test_obs02_documents_four_new_codes() -> None:
    body = (Path(__file__).resolve().parents[1] / "docs/observability/OBS-02_audit_action_codes.md").read_text(encoding="utf-8")
    for code in (
        "kyc_edd_completed",
        "kyc_edd_trigger_listed",
        "kyc_edd_trigger_detail_viewed",
        "kyc_edd_evaluated",
    ):
        assert f"| {code} |" in body, (
            f"OBS-02 must document {code} so audit reviewers can trace it"
        )


def test_frontend_kyc_edd_page_present_with_5_endpoint_bindings() -> None:
    page = (Path(__file__).resolve().parents[1] / "apps/web/src/pages/KycEddPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "export function KycEddPage" in page
    assert '"/kyc-edd/triggers"' in page
    assert "/kyc-edd/triggers/${selectedId}" in page  # detail
    assert "/kyc-edd/triggers/${id}/reassess" in page
    assert "/kyc-edd/triggers/${id}/complete" in page
    # WRITE_ROLES gate excludes AUDIT_VIEWER/BRANCH_MANAGER
    assert 'WRITE_ROLES = new Set(["PB", "WM", "ADMIN"])' in page
