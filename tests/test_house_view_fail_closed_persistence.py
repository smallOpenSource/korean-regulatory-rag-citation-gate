"""T265 fail_closed_reason_code persistence — Wave-Audit-Defect-Fix A5 / CR-6.

Audit defect CR-6: routers/house_views.py POST /generate-content received a
HouseViewGenResult with fail_closed_reason_code = 'LLM07_LEAKAGE_REDACTED' /
'PROMPT_INJECTION_DETECTED' / 'PARSE_ERROR' but dropped it on the floor —
advance_to_generated had no kwarg for it, the house_views row had no column
for it, and the audit_log detail omitted it. Safety branches were therefore
invisible in audit.

Acceptance (plan §6 Wave A A5 row, line 294):
  * advance_to_generated accepts ``fail_closed_reason_code`` kwarg.
  * V055 migration adds ``house_views.fail_closed_reason_code`` column.
  * Router forwards ``result.fail_closed_reason_code`` to the repo call.
  * Unit test 3 reason_code branch coverage (LLM07 / INJECTION / PARSE).
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

from apps.api.harness.repositories.house_views import (
    ADVANCE_TO_GENERATED_SQL,
    advance_to_generated,
)
from apps.api.harness.services.house_view import HouseViewGenResult


def test_advance_to_generated_accepts_fail_closed_reason_code_kwarg() -> None:
    sig = inspect.signature(advance_to_generated)
    assert "fail_closed_reason_code" in sig.parameters, (
        "advance_to_generated must accept fail_closed_reason_code kwarg "
        "to forward T265 safety branch evidence to the row"
    )
    param = sig.parameters["fail_closed_reason_code"]
    assert param.default is None, (
        "fail_closed_reason_code must default to None to preserve "
        "success-path callers"
    )


def test_advance_to_generated_sql_writes_and_returns_column() -> None:
    assert "fail_closed_reason_code = $11" in ADVANCE_TO_GENERATED_SQL, (
        "ADVANCE_TO_GENERATED_SQL must SET fail_closed_reason_code from "
        "the 11th positional parameter (V055 column added by Wave-Audit-Defect-Fix A5)"
    )
    _, returning_section = ADVANCE_TO_GENERATED_SQL.split("RETURNING", 1)
    assert "fail_closed_reason_code" in returning_section, (
        "RETURNING clause must surface fail_closed_reason_code so callers can "
        "audit which safety branch fired"
    )


def test_v055_migration_present_and_adds_column() -> None:
    migration = Path(__file__).resolve().parent.parent / "db" / "migrations" / (
        "V055__house_view_fail_closed_reason.sql"
    )
    assert migration.exists(), f"V055 migration not at {migration}"
    body = migration.read_text(encoding="utf-8")
    assert body.startswith("/* sql_id: v055_house_view_fail_closed_reason */"), (
        "V055 first line must be the canonical /* sql_id: ... */ comment "
        "per feedback-v-sql-sql-id-validator"
    )
    assert "ALTER TABLE house_views" in body
    assert "fail_closed_reason_code" in body
    assert "ADD COLUMN IF NOT EXISTS" in body, "must be idempotent re-run safe"


def test_router_forwards_fail_closed_reason_code_to_repo() -> None:
    router = Path(__file__).resolve().parent.parent / "apps" / "api" / "harness" / (
        "api"
    ) / "routers" / "house_views.py"
    source = router.read_text(encoding="utf-8")
    assert "fail_closed_reason_code=result.fail_closed_reason_code" in source, (
        "router must forward result.fail_closed_reason_code to advance_to_generated "
        "so all 3 safety branches (LLM07_LEAKAGE_REDACTED / PROMPT_INJECTION_DETECTED "
        "/ PARSE_ERROR) end up on the row, not just success paths"
    )
    assert '"fail_closed_reason_code": result.fail_closed_reason_code' in source, (
        "audit_log detail must include fail_closed_reason_code so audit search "
        "can find safety-branch invocations without joining house_views"
    )


def test_three_reason_code_branches_covered() -> None:
    branches = {
        "LLM07_LEAKAGE_REDACTED": "redactor reported leakage / instruction echo",
        "PROMPT_INJECTION_DETECTED": "output-side Content-Safety blocked",
        "PARSE_ERROR": "JSON parse failed after redaction",
    }
    service = (
        Path(__file__).resolve().parent.parent / "apps" / "api" / "harness"
        / "services" / "house_view.py"
    )
    source = service.read_text(encoding="utf-8")
    for code in branches:
        assert f'"{code}"' in source, (
            f"service must assign {code} on its safety branch (T265)"
        )

    for code in branches:
        row = HouseViewGenResult(
            content={},
            model="m",
            generated_at=datetime(2026, 5, 21, tzinfo=UTC),
            prompt_tokens=0,
            completion_tokens=0,
            inputs_hash="h",
            fail_closed_reason_code=code,
        )
        assert row.fail_closed_reason_code == code
