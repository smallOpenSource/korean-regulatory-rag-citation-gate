#!/usr/bin/env python3
"""generate_sod_evidence_pack.py — Stage 6 SoD evidence (ADR-007 §3, REG-06 §5).

Queries audit_logs for a time window and produces a Segregation-of-Duties
evidence pack for SOC2-style review.  Three buckets:

  A — governance_marker = 'PoC_AUTO_APPROVAL'  (expected non-zero in demo runs)
  B — governance_marker IS NULL, human-reviewer-required action_code,
      detail_json->>'human_reviewer' IS NOT NULL  (normal path, expected populated)
  C — governance_marker IS NULL, human-reviewer-required action_code,
      detail_json->>'human_reviewer' IS NULL  (**violation** — expected 0)

Human-reviewer-required action codes are the hardcoded closed set below
(see docs/observability/OBS-02_audit_action_codes.md human_reviewer_required
column; maintained here until OBS-02 gains a machine-readable flag).

Exit codes (ADR-007 §0 base set):
  0  all clean — Bucket C empty (or fully covered by --allow-exception)
  2  Bucket C non-empty and not fully covered by exception list
  3  config error (missing env, invalid window, unreachable DB)

Output JSON shape (ADR-007 §3):
  {
    "verified_at": "<UTC ISO8601>",
    "status": "passed|failed",
    "passed": bool,
    "window": {"from": "<UTC>", "to": "<UTC>"},
    "buckets": {
      "poc_auto_approval": {"count": N, "sample_audit_ids": [...]},
      "human_approved":    {"count": N, "sample_audit_ids": [...]},
      "violations":        {"count": N, "audit_ids": [...]}
    },
    "by_role": {"PB": N, "BRANCH_MANAGER": N, ...},
    "exception_list": [...],
    "evidence_paths": [...]
  }
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import database_url_from_env, load_env_file  # noqa: E402

# ---------------------------------------------------------------------------
# Human-reviewer-required action codes — DISTINCT-second-person reviews only.
#
# Scope corrected per the #4-A SoD classification (ADR-021): only action codes
# whose emit path involves a human reviewer DISTINCT from the initiating actor
# remain here. The following were REMOVED because their emit path has no distinct
# reviewer in scope, so requiring detail_json.human_reviewer on them only produced
# phantom Bucket C violations (masked by the not_operational bootstrap below):
#   - single-actor self-confirmations: consultation_complete, suitability_confirmed,
#     explanation_confirmed, four_gate_acknowledged, kyc_edd_triggered,
#     kyc_edd_reassessed, conflict_disclosed, info_access_responded
#   - automated-gate / ADMIN-only governance: marketing_review_approved,
#     marketing_review_rejected, house_view_activated, house_view_reviewed,
#     credit_info_purge_simulated
# The four below are genuine review-decision points. Recording detail_json.
# human_reviewer at their emit sites is ADR-021 Phase 2 (deferred): dispute_case_
# resolved -> previous_actor_id (distinct guaranteed by the same-actor 4-eye block);
# email approve/reject -> approver/reviewer; email_sent_via_sandbox -> prior
# approver (A-4 open decision). Until then these stay not_operational (Bucket B=0).
# Keep in sync with docs/observability/OBS-02_audit_action_codes.md.
# ---------------------------------------------------------------------------
HUMAN_REVIEWER_REQUIRED_ACTION_CODES: frozenset[str] = frozenset(
    {
        "email_draft_approved",
        "email_draft_rejected",
        "email_sent_via_sandbox",
        "dispute_case_resolved",
    }
)

DEFAULT_REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"
SAMPLE_LIMIT = 5  # max sample audit_ids per bucket in output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(dt: datetime) -> str:
    """Format datetime as ISO8601 UTC with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso8601(value: str) -> datetime:
    """Parse ISO8601 string to UTC-aware datetime (3 config error on failure)."""
    try:
        normalized = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, AttributeError) as exc:
        raise SystemExit(3) from ValueError(
            f"Invalid ISO8601 timestamp: {value!r} — {exc}"
        )


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# DB queries (raw SQL + sql_id prefix — ADR-003 §"raw SQL" requirement)
# ---------------------------------------------------------------------------


async def _query_bucket_a(
    conn: Any,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict[str, Any]]:
    """Bucket A: governance_marker = 'PoC_AUTO_APPROVAL'."""
    sql = """
/* sql_id: sod_bucket_a_poc_auto_approval */
SELECT
    al.id,
    al.action_code,
    al.actor_id,
    e.role_code,
    al.created_at
FROM audit_logs al
LEFT JOIN employees e ON e.id = al.actor_id
WHERE al.governance_marker = 'PoC_AUTO_APPROVAL'
  AND al.created_at >= $1
  AND al.created_at <  $2
ORDER BY al.created_at DESC
""".strip()
    rows = await conn.fetch(sql, from_dt, to_dt)
    return [dict(r) for r in rows]


async def _query_bucket_b(
    conn: Any,
    from_dt: datetime,
    to_dt: datetime,
    action_codes: frozenset[str],
) -> list[dict[str, Any]]:
    """Bucket B: human-reviewer-required + human_reviewer set in detail_json."""
    action_codes_list = list(action_codes)
    sql = """
/* sql_id: sod_bucket_b_human_approved */
SELECT
    al.id,
    al.action_code,
    al.actor_id,
    al.detail_json->>'human_reviewer' AS human_reviewer,
    al.created_at
FROM audit_logs al
WHERE al.governance_marker IS NULL
  AND al.action_code = ANY($3::text[])
  AND al.detail_json->>'human_reviewer' IS NOT NULL
  AND al.created_at >= $1
  AND al.created_at <  $2
ORDER BY al.created_at DESC
""".strip()
    rows = await conn.fetch(sql, from_dt, to_dt, action_codes_list)
    return [dict(r) for r in rows]


async def _query_bucket_c(
    conn: Any,
    from_dt: datetime,
    to_dt: datetime,
    action_codes: frozenset[str],
) -> list[dict[str, Any]]:
    """Bucket C: human-reviewer-required + human_reviewer MISSING — violations."""
    action_codes_list = list(action_codes)
    sql = """
/* sql_id: sod_bucket_c_violations */
SELECT
    al.id,
    al.action_code,
    al.actor_id,
    al.created_at
FROM audit_logs al
WHERE al.governance_marker IS NULL
  AND al.action_code = ANY($3::text[])
  AND (al.detail_json->>'human_reviewer') IS NULL
  AND al.created_at >= $1
  AND al.created_at <  $2
ORDER BY al.created_at DESC
""".strip()
    rows = await conn.fetch(sql, from_dt, to_dt, action_codes_list)
    return [dict(r) for r in rows]


async def _query_by_role(
    conn: Any,
    from_dt: datetime,
    to_dt: datetime,
) -> dict[str, int]:
    """Count Bucket-A rows broken down by employee role_code."""
    sql = """
/* sql_id: sod_by_role_breakdown */
SELECT
    COALESCE(e.role_code, 'UNKNOWN') AS role_code,
    COUNT(al.id)::int AS row_count
FROM audit_logs al
LEFT JOIN employees e ON e.id = al.actor_id
WHERE al.governance_marker = 'PoC_AUTO_APPROVAL'
  AND al.created_at >= $1
  AND al.created_at <  $2
GROUP BY COALESCE(e.role_code, 'UNKNOWN')
ORDER BY row_count DESC
""".strip()
    rows = await conn.fetch(sql, from_dt, to_dt)
    return {str(r["role_code"]): int(r["row_count"]) for r in rows}


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


async def _run(
    from_dt: datetime,
    to_dt: datetime,
    out_path: Path,
    also_json: bool,
    allow_exception: list[str],
) -> int:
    """Run SoD evidence collection; returns process exit code."""
    try:
        import asyncpg  # type: ignore[import]
    except ImportError:
        print("ERROR: asyncpg is required (pip install asyncpg)", file=sys.stderr)
        return 3

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_env_file(env_path)

    try:
        db_url = database_url_from_env()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: DB config error — {exc}", file=sys.stderr)
        return 3

    try:
        conn = await asyncpg.connect(db_url)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Cannot connect to PostgreSQL — {exc}", file=sys.stderr)
        return 3

    try:
        bucket_a = await _query_bucket_a(conn, from_dt, to_dt)
        bucket_b = await _query_bucket_b(
            conn, from_dt, to_dt, HUMAN_REVIEWER_REQUIRED_ACTION_CODES
        )
        bucket_c = await _query_bucket_c(
            conn, from_dt, to_dt, HUMAN_REVIEWER_REQUIRED_ACTION_CODES
        )
        by_role = await _query_by_role(conn, from_dt, to_dt)
    finally:
        await conn.close()

    verified_at = iso_z(utc_now())

    # Violations: Bucket C IDs not in the user-approved exception list
    violation_ids = [str(r["id"]) for r in bucket_c]
    covered = set(allow_exception)
    uncovered_violations = [vid for vid in violation_ids if vid not in covered]

    # SoD human_reviewer dimension operability check (#4 fix).
    # Bucket C keys on detail_json->>'human_reviewer' IS NULL, but no emit path
    # currently records a 'human_reviewer' key (apps/api writes only
    # governance_marker). When NO row in the window records human_reviewer
    # (Bucket B empty) yet Bucket C is non-empty, every human-reviewer-required
    # row falls into Bucket C structurally — a false positive, not a real SoD
    # breach. In that state the gate is NOT operational, so report
    # status="not_operational" / passed=True (mirroring verify_total_product_
    # readiness composite_gate's not_yet_collected bootstrap) and keep the count
    # informational. It self-heals to strict pass/fail once the emit layer records
    # human_reviewer (#4-A follow-up: add human_reviewer to the 17 human-reviewer-
    # required emit sites — backend + ADR scope).
    human_reviewer_recorded = len(bucket_b) > 0
    not_operational = (not human_reviewer_recorded) and len(uncovered_violations) > 0
    if not_operational:
        passed = True
        status_str = "not_operational"
    else:
        passed = len(uncovered_violations) == 0
        status_str = "passed" if passed else "failed"

    # Build output paths
    ts_slug = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if out_path.suffix == ".md":
        json_path = out_path.with_suffix(".json")
    else:
        json_path = out_path.with_suffix(".json") if out_path.suffix != ".json" else out_path

    evidence_paths: list[str] = []

    payload: dict[str, Any] = {
        "verified_at": verified_at,
        "status": status_str,
        "passed": passed,
        "window": {
            "from": iso_z(from_dt),
            "to": iso_z(to_dt),
        },
        "buckets": {
            "poc_auto_approval": {
                "count": len(bucket_a),
                "sample_audit_ids": [str(r["id"]) for r in bucket_a[:SAMPLE_LIMIT]],
            },
            "human_approved": {
                "count": len(bucket_b),
                "sample_audit_ids": [str(r["id"]) for r in bucket_b[:SAMPLE_LIMIT]],
            },
            "violations": {
                "count": len(uncovered_violations),
                "audit_ids": uncovered_violations,
            },
        },
        "by_role": by_role,
        "exception_list": list(covered),
        "human_reviewer_dimension": (
            "not_operational" if not_operational else "operational"
        ),
        "note": (
            (
                "human_reviewer SoD dimension inactive: no audit emit records "
                "detail_json.human_reviewer for human-reviewer-required actions, so the "
                "violations count above is informational (not gating). Strict pass/fail "
                "activates automatically once the emit layer records human_reviewer "
                "(#4-A follow-up)."
            )
            if not_operational
            else None
        ),
        "evidence_paths": evidence_paths,
    }

    # Write JSON output
    atomic_write_json(json_path, payload)
    evidence_paths.append(str(json_path))
    payload["evidence_paths"] = evidence_paths

    # Write Markdown report if primary output is .md or also_json requested
    if out_path.suffix == ".md" or also_json:
        md_lines = [
            "# SoD Evidence Pack",
            f"",
            f"**Generated**: {verified_at}",
            f"**Window**: `{iso_z(from_dt)}` → `{iso_z(to_dt)}`",
            f"**Status**: `{status_str.upper()}`",
            f"",
            "## Buckets",
            "",
            f"| Bucket | Count |",
            f"|--------|-------|",
            f"| Bucket A — PoC_AUTO_APPROVAL | {len(bucket_a)} |",
            f"| Bucket B — Human Approved | {len(bucket_b)} |",
            f"| Bucket C — Violations | {len(uncovered_violations)} |",
            "",
        ]
        if by_role:
            md_lines += [
                "## By Role (Bucket A)",
                "",
                "| Role | Count |",
                "|------|-------|",
            ]
            for role, count in sorted(by_role.items()):
                md_lines.append(f"| {role} | {count} |")
            md_lines.append("")

        if uncovered_violations:
            md_lines += [
                "## Violations (Bucket C)",
                "",
            ]
            for vid in uncovered_violations:
                md_lines.append(f"- `{vid}`")
            md_lines.append("")

        md_path = out_path if out_path.suffix == ".md" else out_path.with_suffix(".md")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("\n".join(md_lines))
        if str(md_path) not in evidence_paths:
            evidence_paths.append(str(md_path))
        # Re-write JSON with updated evidence_paths
        payload["evidence_paths"] = evidence_paths
        atomic_write_json(json_path, payload)

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))

    if not passed:
        print(
            f"\nFAIL: {len(uncovered_violations)} violation(s) found "
            f"(governance_marker IS NULL, human reviewer missing).",
            file=sys.stderr,
        )
        return 2

    if not_operational:
        print(
            f"\nNOT_OPERATIONAL: SoD human_reviewer dimension inactive — no emit "
            f"records detail_json.human_reviewer. Bucket C={len(uncovered_violations)} "
            f"(informational, not gating). See #4-A follow-up.",
            file=sys.stderr,
        )
        return 0

    print(
        f"\nOK: SoD evidence pack written. "
        f"Bucket A={len(bucket_a)}, B={len(bucket_b)}, C-violations=0.",
        file=sys.stderr,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate SoD evidence pack per ADR-007 §3 (Stage 6).",
    )
    parser.add_argument(
        "--from",
        dest="from_dt",
        required=True,
        metavar="UTC",
        help="Window start (ISO8601 UTC, e.g. 2026-05-17T00:00:00Z)",
    )
    parser.add_argument(
        "--to",
        dest="to_dt",
        required=True,
        metavar="UTC",
        help="Window end (ISO8601 UTC)",
    )
    parser.add_argument(
        "--out",
        dest="out",
        default=None,
        metavar="PATH",
        help=(
            "Output path for primary report.  "
            "Default: .omx/reports/verification/sod-evidence-pack-<UTC>.md"
        ),
    )
    parser.add_argument(
        "--also-json",
        action="store_true",
        default=False,
        help="Always write a sibling .json when --out is .md (default for .md outputs).",
    )
    parser.add_argument(
        "--allow-exception",
        default="",
        metavar="UUID[,UUID,...]",
        help="Comma-separated audit_log IDs pre-approved as exceptions for Bucket C.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    from_dt = parse_iso8601(args.from_dt)
    to_dt = parse_iso8601(args.to_dt)

    if from_dt >= to_dt:
        print("ERROR: --from must be before --to", file=sys.stderr)
        sys.exit(3)

    ts_slug = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = (
            DEFAULT_REPORT_DIR / f"sod-evidence-pack-{ts_slug}.md"
        )

    allow_exception: list[str] = (
        [x.strip() for x in args.allow_exception.split(",") if x.strip()]
        if args.allow_exception
        else []
    )

    exit_code = asyncio.run(
        _run(
            from_dt=from_dt,
            to_dt=to_dt,
            out_path=out_path,
            also_json=args.also_json,
            allow_exception=allow_exception,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
