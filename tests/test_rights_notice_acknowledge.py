"""Wave-Audit-Defect-Fix C6 — POST /rights-notice/acknowledge structural verification.

Audit defect C6: RightsNoticePage frontend had a `setTimeout`-based stub
instead of a real POST, so PB acknowledgement of the four-rights notice
left no audit trail. The backend now exposes
``POST /rights-notice/acknowledge`` which emits canonical
``rights_notice_acknowledged`` (V058) paired with the earlier
``rights_notice_issued`` (V022) row.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from apps.api.harness.api.routers import rights_notice as rights_notice_router
from apps.api.harness.core.audit import (
    CANONICAL_AUDIT_ACTION_CODES,
    is_valid_audit_action,
)


def test_v058_migration_seeds_rights_notice_acknowledged() -> None:
    migration = (Path(__file__).resolve().parents[1] / "db/migrations/V058__rights_notice_acknowledged_audit_code.sql")
    assert migration.exists()
    body = migration.read_text(encoding="utf-8")
    assert body.startswith(
        "/* sql_id: v058_rights_notice_acknowledged_audit_code */"
    ), "V058 first line must be canonical /* sql_id: ... */ per V-sql validator"
    assert "'rights_notice_acknowledged'" in body
    assert "ON CONFLICT (action_code) DO NOTHING" in body, (
        "V058 must be idempotent re-run safe"
    )


def test_rights_notice_acknowledged_is_canonical() -> None:
    assert "rights_notice_acknowledged" in CANONICAL_AUDIT_ACTION_CODES, (
        "rights_notice_acknowledged must be in Python canonical tuple — "
        "V058 seeds the DB row but the Python registration is what gates "
        "is_valid_audit_action() at emit time"
    )
    assert is_valid_audit_action("rights_notice_acknowledged") is True


def test_acknowledge_endpoint_exists_on_router() -> None:
    handler = getattr(rights_notice_router, "acknowledge_rights_notice", None)
    assert handler is not None, (
        "rights_notice router must expose acknowledge_rights_notice "
        "(POST /rights-notice/acknowledge)"
    )
    sig = inspect.signature(handler)
    assert {"request", "payload", "authorization"} <= set(sig.parameters), (
        "acknowledge_rights_notice must take request + payload + authorization"
    )


def test_acknowledge_source_emits_canonical_action_code() -> None:
    source = Path(rights_notice_router.__file__).read_text(encoding="utf-8")
    assert 'action_code="rights_notice_acknowledged"' in source, (
        "acknowledge handler must emit canonical rights_notice_acknowledged"
    )
    assert "/rights-notice/acknowledge" in source, (
        "router must register POST /rights-notice/acknowledge path"
    )


def test_frontend_uses_real_post_not_settimeout_stub() -> None:
    page = (Path(__file__).resolve().parents[1] / "apps/web/src/pages/RightsNoticePage.tsx").read_text(
        encoding="utf-8"
    )
    assert "postResource" in page, "frontend must call postResource for ack"
    assert "/rights-notice/acknowledge" in page, (
        "frontend must call the canonical POST path"
    )
    assert "useMutation" in page, "frontend must use react-query useMutation"
    assert "consultation_id" in page, (
        "frontend must pass consultation_id in the POST body"
    )
    # Old stub line must be gone
    assert (
        "// In production this would POST to /consultations/{id}/rights-notice-ack"
        not in page
    ), "stub comment must be removed"
