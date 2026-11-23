"""Wave-Audit-Defect-Fix E5 — audit_logs.event_ts column migration.

Plan §6 line 452: ADD COLUMN event_ts default (logical event time, separate
from physical created_at). Plan originally named this V058 but Wave C
consumed V058-V060 (rights_notice_acknowledged + dispute_responded + 4
kyc_edd codes), so V061 is the slot here.

Structural verification only — runtime scipy.stats timestamp_spread test
requires a live database and is owed to Wave F4.
"""

from __future__ import annotations

from pathlib import Path


def test_v061_audit_event_ts_migration_present() -> None:
    migration = (Path(__file__).resolve().parents[1] / "db/migrations/V061__audit_event_ts.sql")
    assert migration.exists()
    body = migration.read_text(encoding="utf-8")
    assert body.startswith("/* sql_id: v061_audit_event_ts */"), (
        "V061 first line must be the canonical /* sql_id: ... */ comment "
        "per feedback-v-sql-sql-id-validator"
    )


def test_v061_adds_event_ts_column_with_default() -> None:
    body = (Path(__file__).resolve().parents[1] / "db/migrations/V061__audit_event_ts.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE audit_logs" in body
    assert "ADD COLUMN IF NOT EXISTS event_ts" in body, (
        "V061 must idempotently add event_ts column"
    )
    assert "TIMESTAMPTZ" in body
    assert "SET DEFAULT now()" in body, (
        "new inserts get event_ts=now() automatically when caller does not "
        "set it explicitly"
    )


def test_v061_documents_coalesce_pattern_for_legacy_rows() -> None:
    """audit_logs is append-only (V008 trg_audit_logs_no_update + V019
    no_truncate). The original "UPDATE audit_logs SET event_ts =
    created_at" backfill plan from Iter3 is invalid because the trigger
    rejects every row-level UPDATE. The V061 SQL therefore documents the
    COALESCE(event_ts, created_at) pattern callers must use on legacy
    rows instead of running a forbidden backfill UPDATE.
    """
    body = (Path(__file__).resolve().parents[1] / "db/migrations/V061__audit_event_ts.sql").read_text(encoding="utf-8")
    assert "append-only" in body, (
        "the migration must call out the append-only invariant explicitly"
    )
    assert "COALESCE(event_ts, created_at)" in body, (
        "callers reading legacy rows need the documented COALESCE pattern"
    )


def test_v061_creates_event_ts_index() -> None:
    body = (Path(__file__).resolve().parents[1] / "db/migrations/V061__audit_event_ts.sql").read_text(encoding="utf-8")
    assert "CREATE INDEX IF NOT EXISTS idx_audit_event_ts" in body, (
        "event_ts queries (e.g. event-time DESC reads) need an index"
    )


def test_v061_is_additive_not_in_place_edit_of_v054() -> None:
    """V054 in-place edit is forbidden per feedback-on-conflict-id-for-mutable-content."""
    v054 = (Path(__file__).resolve().parents[1] / "db/migrations/V054__v8_audit_action_codes_and_cleanup.sql").read_text(encoding="utf-8")
    assert "event_ts" not in v054, (
        "event_ts must not be added to V054 — additive series only"
    )
