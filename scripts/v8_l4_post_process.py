#!/usr/bin/env python
"""v8_l4_post_process.py — Stage 3 cycle 2/3 framework deliverable

L4 cross-field detector post-process pass.

Cycle 1/2 BFS visit_cell ran scan_l4({}) with empty fields (no DOM field
extraction implemented inline). This script re-runs L4 against per-cell
entity fields fetched from DB.

Input:
  .omc/state/v8-traversal/cycle_N/visited.jsonl

Output:
  .omc/state/v8-traversal/cycle_N/l4_findings.jsonl  (per-cell L4 findings)
  .omc/state/v8-traversal/cycle_N/l4_summary.json    (aggregate)

Entity binding per route (mirrors v8_cell_space.ROUTE_ENTITY):
  /consultations/:id → consultations row (status, summary, error_message, ...)
  /house-views/:id   → house_views row (status, activation_period, ...)
  /house-views/:id/activate → same (with activation lifecycle)
  /nba (list page) → sample NBA action
  /email-drafts (list page) → sample email draft
  /aftercare (list page) → sample aftercare event
  /batch (list page) → batch_jobs not in DB; skipped
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
from typing import Any

import asyncpg  # type: ignore[import-not-found]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
FIXTURE_IDS = REPO_ROOT / ".omc/state/v8-fixture-ids.json"
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from v8_detector_L4_cross_field import scan_l4  # noqa: E402


def load_env_var(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    if not m:
        return ""
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
        val = val[1:-1]
    return val


async def fetch_entity_fields(conn: Any, route: str, fixtures: dict[str, str]) -> dict[str, Any] | None:
    """Fetch entity fields for a given route via real DB query."""
    if "/consultations/:" in route:
        row = await conn.fetchrow(
            "SELECT status_code AS status, summary, "
            "consultation_at AS due_at FROM consultations WHERE id = $1::uuid",
            fixtures["consultationId"],
        )
        if row is None:
            return None
        d = dict(row)
        d["entity"] = "consultations"
        return d
    if "/house-views/:" in route:
        row = await conn.fetchrow(
            "SELECT status_code AS status, activated_at AS activation_period, "
            "superseded_at AS superseded_by FROM house_views WHERE id = $1::uuid",
            fixtures["houseViewId"],
        )
        if row is None:
            return None
        d = dict(row)
        d["entity"] = "house_views"
        return d
    if route == "/email-drafts":
        row = await conn.fetchrow(
            "SELECT status_code AS status, "
            "transport_message_id AS message_id, "
            "approved_by_id AS approved_by, "
            "failure_reason_code AS error_message FROM email_drafts WHERE id = $1::uuid",
            fixtures["emailDraftId"],
        )
        if row is None:
            return None
        d = dict(row)
        d["entity"] = "email_drafts"
        return d
    if route == "/aftercare":
        row = await conn.fetchrow(
            "SELECT status_code AS status, completion_notes AS resolution_note "
            "FROM aftercare_events WHERE id = $1::uuid",
            fixtures["aftercareId"],
        )
        if row is None:
            return None
        d = dict(row)
        d["entity"] = "aftercare_events"
        return d
    if route == "/nba":
        row = await conn.fetchrow(
            "SELECT status_code AS status, snoozed_until "
            "FROM nba_actions WHERE id = $1::uuid",
            fixtures["nbaId"],
        )
        if row is None:
            return None
        d = dict(row)
        d["entity"] = "nba_actions"
        return d
    return None  # no entity binding (dashboard, customers, audit, etc.)


async def main_async(args: argparse.Namespace) -> int:
    cycle_dir = REPO_ROOT / ".omc/state/v8-traversal" / f"cycle_{args.cycle}"
    visited_path = cycle_dir / "visited.jsonl"
    if not visited_path.exists():
        print(f"ERROR: {visited_path} not found")
        return 2

    with FIXTURE_IDS.open() as fh:
        fixtures: dict[str, str] = json.load(fh)

    rows: list[dict[str, Any]] = []
    with visited_path.open() as fh:
        for line in fh:
            rows.append(json.loads(line))

    dsn = load_env_var("DATABASE_URL")
    conn = await asyncpg.connect(dsn=dsn, timeout=10.0)

    # Cache entity fields per route (DB query once per unique route)
    fields_cache: dict[str, dict[str, Any] | None] = {}
    try:
        unique_routes = {r["cell"]["route"] for r in rows}
        for route in unique_routes:
            fields_cache[route] = await fetch_entity_fields(conn, route, fixtures)
    finally:
        await conn.close()

    findings_path = cycle_dir / "l4_findings.jsonl"
    summary_path = cycle_dir / "l4_summary.json"
    total_defect = 0
    defect_per_combo: dict[str, int] = {}
    defect_per_route: dict[str, int] = {}
    with findings_path.open("w") as fh:
        for r in rows:
            cell = r["cell"]
            fields = fields_cache.get(cell["route"])
            if fields is None:
                continue
            findings = scan_l4(fields)
            if not findings:
                continue
            total_defect += 1
            defect_per_route[cell["route"]] = defect_per_route.get(cell["route"], 0) + 1
            for f in findings:
                defect_per_combo[f.combo_id] = defect_per_combo.get(f.combo_id, 0) + 1
            fh.write(json.dumps({
                "cell": cell,
                "fields": {k: (str(v) if v is not None else None) for k, v in fields.items()},
                "L4_findings": [
                    {"combo_id": f.combo_id, "description": f.description}
                    for f in findings
                ],
            }, ensure_ascii=False) + "\n")

    summary = {
        "cycle": args.cycle,
        "visited_total": len(rows),
        "L4_defect_cells": total_defect,
        "defect_rate_pct": round(total_defect * 100 / max(len(rows), 1), 2),
        "defect_per_combo": defect_per_combo,
        "defect_per_route": defect_per_route,
        "entity_routes_inspected": [r for r, f in fields_cache.items() if f is not None],
        "findings_path": str(findings_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="L4 cross-field post-process (cycle N)")
    p.add_argument("--cycle", type=int, required=True)
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
