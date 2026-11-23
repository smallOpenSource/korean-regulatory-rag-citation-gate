"""Wave-Audit-Defect-Fix A6 — quarantine_released audit emit verify.

Audit defect: V045 seeded ``quarantine_released`` into the audit_action_codes
DB table and the router (apps/api/harness/api/routers/batch.py:162) emits it,
but the Python-side canonical tuple (core/audit.py CANONICAL_AUDIT_ACTION_CODES)
was missing it. Result: ``is_valid_audit_action('quarantine_released')`` returned
False so any contract test gating on the canonical tuple silently misclassified
the emit as a phantom code.

Acceptance:
  * ``quarantine_released`` is a member of CANONICAL_AUDIT_ACTION_CODES.
  * ``is_valid_audit_action('quarantine_released')`` returns True.
  * Router emits the canonical code with the chunk_id + reason in detail.
  * OBS-02 documents the code in the REG-04 section.
"""

from __future__ import annotations

from pathlib import Path

from apps.api.harness.core.audit import (
    CANONICAL_AUDIT_ACTION_CODES,
    is_valid_audit_action,
)


def test_quarantine_released_in_canonical_tuple() -> None:
    assert "quarantine_released" in CANONICAL_AUDIT_ACTION_CODES, (
        "quarantine_released must be canonical: V045 seeds it into the DB "
        "audit_action_codes table and routers/batch.py:162 emits it; missing "
        "Python registration creates a silent gap between DB + emit + canonical"
    )


def test_quarantine_released_passes_validation() -> None:
    assert is_valid_audit_action("quarantine_released") is True


def test_router_emits_quarantine_released_with_detail() -> None:
    router = (
        Path(__file__).resolve().parent.parent / "apps" / "api" / "harness"
        / "api" / "routers" / "batch.py"
    )
    source = router.read_text(encoding="utf-8")
    assert 'action_code="quarantine_released"' in source, (
        "release_document_chunk handler must emit action_code='quarantine_released'"
    )
    assert "quarantine_reason_code" in source, (
        "audit detail must include quarantine_reason_code so the release event "
        "preserves why the chunk was quarantined in the first place"
    )


def test_obs02_documents_quarantine_released() -> None:
    obs02 = (
        Path(__file__).resolve().parent.parent / "docs" / "observability"
        / "OBS-02_audit_action_codes.md"
    )
    body = obs02.read_text(encoding="utf-8")
    assert "| quarantine_released |" in body, (
        "OBS-02 must list quarantine_released in the REG-04 section"
    )


def test_v045_seeds_quarantine_released() -> None:
    migration = (
        Path(__file__).resolve().parent.parent / "db" / "migrations"
        / "V045__audit_action_codes_house_view_kyc_quarantine.sql"
    )
    body = migration.read_text(encoding="utf-8")
    assert "'quarantine_released'" in body, (
        "V045 must seed quarantine_released into the DB audit_action_codes table"
    )
