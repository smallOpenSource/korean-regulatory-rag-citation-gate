"""Wave-Audit-Defect-Fix C7 — dispute endpoints role gating + RESPONDED audit.

Audit defect C7: routers/disputes.py had no role gate beyond authentication,
so any staff (including AUDIT_VIEWER) could open / list / update disputes — a
regulatory audit gap for REG-01 §36 분쟁조정. Additionally PATCH only emitted
audit on RESOLVED, leaving OPEN→RESPONDED invisible in audit_logs.

Acceptance:
  * 3 write endpoints (POST /disputes, PATCH /disputes/{id}, seed-synthetic
    already had ADMIN) reject non-PB/WM/ADMIN with 403.
  * GET /disputes restricted to staff (PB/WM/ADMIN/AUDIT_VIEWER).
  * PATCH new_status=RESPONDED emits canonical dispute_responded (V059).
  * dispute_responded is in CANONICAL_AUDIT_ACTION_CODES.
  * V059 migration first line carries the canonical /* sql_id: ... */ comment.
"""

from __future__ import annotations

from pathlib import Path

from apps.api.harness.api.routers import disputes as disputes_router
from apps.api.harness.core.audit import (
    CANONICAL_AUDIT_ACTION_CODES,
    is_valid_audit_action,
)


def test_v059_migration_present_with_sql_id() -> None:
    migration = (Path(__file__).resolve().parents[1] / "db/migrations/V059__dispute_responded_audit_code.sql")
    assert migration.exists()
    body = migration.read_text(encoding="utf-8")
    assert body.startswith(
        "/* sql_id: v059_dispute_responded_audit_code */"
    )
    assert "'dispute_responded'" in body
    assert "ON CONFLICT (action_code) DO NOTHING" in body


def test_dispute_responded_is_canonical() -> None:
    assert "dispute_responded" in CANONICAL_AUDIT_ACTION_CODES
    assert is_valid_audit_action("dispute_responded") is True


def test_write_role_helper_defined() -> None:
    write_set = getattr(disputes_router, "_DISPUTE_WRITE_ROLES", None)
    assert write_set is not None
    assert "PB" in write_set
    assert "WM" in write_set
    assert "ADMIN" in write_set
    assert "AUDIT_VIEWER" not in write_set, (
        "AUDIT_VIEWER must not be allowed to mutate dispute cases"
    )


def test_read_role_helper_defined() -> None:
    read_set = getattr(disputes_router, "_DISPUTE_READ_ROLES", None)
    assert read_set is not None
    for role in ("PB", "WM", "ADMIN", "AUDIT_VIEWER"):
        assert role in read_set, f"{role} should be allowed dispute reads"


def test_router_source_invokes_role_helpers() -> None:
    source = Path(disputes_router.__file__).read_text(encoding="utf-8")
    # POST /disputes (open) must call write-role helper
    assert source.count("_require_dispute_write_role(actor.role_code)") >= 2, (
        "POST and PATCH dispute handlers must both gate on write role"
    )
    # GET /disputes must call read-role helper
    assert "_require_dispute_read_role(actor.role_code)" in source


def test_router_emits_dispute_responded_on_responded_transition() -> None:
    source = Path(disputes_router.__file__).read_text(encoding="utf-8")
    assert 'action_code="dispute_responded"' in source, (
        "PATCH /disputes/{id} new_status=RESPONDED must emit canonical "
        "dispute_responded audit row (was previously silent)"
    )
    assert 'action_code="dispute_case_resolved"' in source, (
        "RESOLVED emit must be preserved (canonical V022)"
    )


def test_obs02_documents_dispute_responded() -> None:
    body = (Path(__file__).resolve().parents[1] / "docs/observability/OBS-02_audit_action_codes.md").read_text(encoding="utf-8")
    assert "| dispute_responded |" in body, (
        "OBS-02 must document dispute_responded in the REG-01 dispute section"
    )
