"""v8 G0a-1: dispatcher dry-run pre-flight — 4 dispatchers × 5 calls = 20 total.

Azure token Δ tolerance = 0 (exact).
Evidence: ``_tokens_in == 0`` and ``_tokens_out == 0`` in the captured
``output_json`` field of every ``INSERT INTO ai_outputs`` execute() call.

Design: Each test creates a fresh :class:`_MockConn` and a synthetic job dict
with ``dry_run=True``. The dispatcher under test returns a canned Korean
fixture without ever reaching ``_invoke_lane`` (the Azure SDK gateway).
The mock connection captures every ``execute()`` call; the test locates the
``INSERT INTO ai_outputs`` call and asserts ``_tokens_in/_tokens_out == 0``
and ``_dry_run is True``.

Expected: 4/4 PASS (one test function per dispatcher, 5 internal calls each).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from apps.api.harness.services.consultation_briefing import run_consultation_briefing
from apps.api.harness.services.email_draft import run_email_draft
from apps.api.harness.services.nba_script import run_nba_script
from apps.api.harness.services.portfolio_analysis import run_portfolio_analysis


# ── Minimal mock connection ───────────────────────────────────────────────────

class _MockConn:
    """Records execute() calls; fetchrow/fetch return no-data (not used in dry_run path)."""

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, sql: str, *args: Any) -> None:  # noqa: ANN401
        self.execute_calls.append((sql, args))

    async def fetchrow(self, sql: str, *args: Any) -> None:  # noqa: ANN401
        return None  # dry_run path must never reach fetchrow

    async def fetch(self, sql: str, *args: Any) -> list[Any]:  # noqa: ANN401
        return []  # dry_run path must never reach fetch


def _make_job(job_type_code: str, resource_type: str) -> dict[str, Any]:
    """Synthetic job dict for dry-run testing (SYN- prefix not needed for id fields)."""
    return {
        "id": str(uuid.uuid4()),
        "job_type_code": job_type_code,
        "resource_type": resource_type,
        "resource_id": str(uuid.uuid4()),
        "requested_by_id": str(uuid.uuid4()),
        "dry_run": True,
    }


def _azure_delta(conn: _MockConn) -> tuple[int, int]:
    """Extract (_tokens_in, _tokens_out) from the INSERT ai_outputs execute() call.

    Searches all captured execute() args for the JSON string that contains
    ``_tokens_in``.  Returns (-1, -1) if no such call was found (test will fail).
    """
    for sql, args in conn.execute_calls:
        if "INSERT INTO ai_outputs" not in sql:
            continue
        for arg in args:
            if isinstance(arg, str) and '"_tokens_in"' in arg:
                payload = json.loads(arg)
                return int(payload.get("_tokens_in", -1)), int(payload.get("_tokens_out", -1))
    return -1, -1


def _dry_run_flag(conn: _MockConn) -> bool:
    """Verify ``_dry_run: true`` is set in the ai_outputs output_json."""
    for sql, args in conn.execute_calls:
        if "INSERT INTO ai_outputs" not in sql:
            continue
        for arg in args:
            if isinstance(arg, str) and '"_dry_run"' in arg:
                return bool(json.loads(arg).get("_dry_run"))
    return False


# ── Test cases (4/4 expected PASS) ───────────────────────────────────────────

def test_email_draft_dry_run() -> None:
    """email_draft: 5 × dry-run calls — synthetic Korean response, Azure Δ=0."""
    for i in range(5):
        conn = _MockConn()
        job = _make_job("email_draft", "email_drafts")
        result = asyncio.run(run_email_draft(conn, job))

        assert isinstance(result, str), f"call {i}: expected str summary, got {result!r}"
        assert "dry_run" in result, f"call {i}: summary missing 'dry_run' marker: {result!r}"
        assert "[SYN]" in result or "dry_run synthetic" in result, (
            f"call {i}: not a synthetic response: {result!r}"
        )

        tokens_in, tokens_out = _azure_delta(conn)
        assert tokens_in == 0, f"call {i}: Azure Δ≠0 — tokens_in={tokens_in}"
        assert tokens_out == 0, f"call {i}: Azure Δ≠0 — tokens_out={tokens_out}"
        assert _dry_run_flag(conn), f"call {i}: _dry_run not set in output_json"


def test_consultation_briefing_dry_run() -> None:
    """consultation_briefing: 5 × dry-run calls — synthetic Korean briefing, Azure Δ=0."""
    for i in range(5):
        conn = _MockConn()
        job = _make_job("consultation_briefing", "consultations")
        result = asyncio.run(run_consultation_briefing(conn, job))

        assert isinstance(result, str), f"call {i}: expected str, got {result!r}"
        assert "dry_run" in result, f"call {i}: summary missing 'dry_run': {result!r}"

        tokens_in, tokens_out = _azure_delta(conn)
        assert tokens_in == 0, f"call {i}: Azure Δ≠0 — tokens_in={tokens_in}"
        assert tokens_out == 0, f"call {i}: Azure Δ≠0 — tokens_out={tokens_out}"
        assert _dry_run_flag(conn), f"call {i}: _dry_run not set in output_json"


def test_nba_script_dry_run() -> None:
    """nba_script: 5 × dry-run calls — synthetic Korean NBA script, Azure Δ=0."""
    for i in range(5):
        conn = _MockConn()
        job = _make_job("nba_script", "nba_actions")
        result = asyncio.run(run_nba_script(conn, job))

        assert isinstance(result, str), f"call {i}: expected str, got {result!r}"
        assert "dry_run" in result, f"call {i}: summary missing 'dry_run': {result!r}"

        tokens_in, tokens_out = _azure_delta(conn)
        assert tokens_in == 0, f"call {i}: Azure Δ≠0 — tokens_in={tokens_in}"
        assert tokens_out == 0, f"call {i}: Azure Δ≠0 — tokens_out={tokens_out}"
        assert _dry_run_flag(conn), f"call {i}: _dry_run not set in output_json"


def test_portfolio_analysis_dry_run() -> None:
    """portfolio_analysis: 5 × dry-run calls — synthetic Korean analysis, Azure Δ=0."""
    for i in range(5):
        conn = _MockConn()
        job = _make_job("portfolio_analysis", "customers")
        result = asyncio.run(run_portfolio_analysis(conn, job))

        assert isinstance(result, str), f"call {i}: expected str, got {result!r}"
        assert "dry_run" in result, f"call {i}: summary missing 'dry_run': {result!r}"

        tokens_in, tokens_out = _azure_delta(conn)
        assert tokens_in == 0, f"call {i}: Azure Δ≠0 — tokens_in={tokens_in}"
        assert tokens_out == 0, f"call {i}: Azure Δ≠0 — tokens_out={tokens_out}"
        assert _dry_run_flag(conn), f"call {i}: _dry_run not set in output_json"
