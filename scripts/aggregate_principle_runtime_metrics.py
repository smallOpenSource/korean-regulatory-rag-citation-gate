#!/usr/bin/env python3
"""ADR-007 §2 RUNTIME aggregator: 금융 AI 7대 원칙 runtime metrics (AC21, AC23).

Aggregates runtime measurements from audit_logs for each of the 7 AI principles,
emitting one JSON file per (principle, metric) pair to docs/ai/measurements/.

Contract:
    Role: harness_audit (V019:38-44 grants SELECT on audit_logs to harness_audit only)
    Env:  DATABASE_URL_HARNESS_AUDIT (preferred for SoD) or DATABASE_URL (PoC fallback)
    Arg:  --window=YYYY-MM-DD — UTC calendar-day deterministic boundary (required)
          --dry-run           — validate args + DB connectivity, emit no files

Denominator (v3.1 NR1+NR7 fix):
    SELECT COUNT(*) FROM audit_logs
    WHERE action_code='AI_CALL_STARTED'
      AND created_at >= window_start AND created_at < window_end
    NOT ai_jobs.STARTED (V008:100 ai_jobs.status_code CHECK omits 'STARTED').

Output schema per plan §1:
    {
      "principle_id": "<P1..P7>",
      "metric": "<metric_name>",
      "value": <float 0.0-1.0>,
      "p95": <float | null>,
      "sample_n": <int>,
      "denominator_source": "audit_logs.AI_CALL_STARTED",
      "denominator": <int>,
      "last_measured_at": "<ISO-8601 UTC>",
      "expires_at": "<ISO-8601 UTC>",
      "source_path": "<relative path>"
    }

Exit codes (ADR-007 §0):
    0 — all metrics written successfully
    2 — one or more metrics failed to compute
    3 — config error (missing env var, invalid window)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENTS_DIR = PROJECT_ROOT / "docs" / "ai" / "measurements"

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

PRINCIPLES = (
    "P1_safety",
    "P2_accountability",
    "P3_transparency",
    "P4_fairness",
    "P5_privacy",
    "P6_security",
    "P7_robustness",
)

# Metrics to collect per principle
PRINCIPLE_METRICS: dict[str, tuple[str, ...]] = {
    "P1_safety": ("fail_closed_rate",),
    "P2_accountability": ("fail_closed_rate",),
    "P3_transparency": ("fail_closed_rate",),
    "P4_fairness": ("pii_false_negative_rate",),
    "P5_privacy": ("pii_false_negative_rate",),
    "P6_security": ("injection_detected_rate",),
    "P7_robustness": (
        "fail_closed_rate",
        "injection_detected_rate",
        "dual_llm_disagreement_rate",
        "faithfulness",
    ),
}

# Action codes (V008:9-29)
_CODE_AI_CALL_STARTED = "AI_CALL_STARTED"
_CODE_AI_FAIL_CLOSED = "ai_fail_closed"
_CODE_INJECTION_DETECTED = "ai_injection_detected"
_CODE_DUAL_LLM_DISAGREEMENT = "ai_quarantine_triggered"
_CODE_PII_FALSE_NEGATIVE = "ai_pii_false_negative"


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_window(window_str: str) -> tuple[datetime, datetime]:
    """Parse YYYY-MM-DD into (window_start, window_end) UTC datetimes."""
    try:
        day = datetime.strptime(window_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(
            f"--window must be YYYY-MM-DD, got {window_str!r}: {exc}"
        ) from exc
    return day, day + timedelta(days=1)


def _get_db_url() -> str:
    """Return audit DB DSN.

    SoD note: V019:38-44 grants harness_audit SELECT on audit_logs when the role
    exists; the IF EXISTS guard means PoC environments without that role still
    pass V019. This collector falls back to DATABASE_URL so PoC deployments
    (single wm_user role) function out of the box. Production deployments that
    enforce 4-role separation should export DATABASE_URL_HARNESS_AUDIT.
    """
    url = os.environ.get("DATABASE_URL_HARNESS_AUDIT", "").strip()
    if not url:
        url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "Neither DATABASE_URL_HARNESS_AUDIT nor DATABASE_URL is set."
        )
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _fetch_denominator(conn, window_start: datetime, window_end: datetime) -> int:
    """Return AI_CALL_STARTED count for the window (NR1+NR7 fix denominator).

    Awaits on the caller's loop; the asyncpg connection stays bound to the single
    event loop opened in _collect_async (see the cross-loop fix in run()).
    """
    val = await conn.fetchval(
        """/* sql_id: aggregate_principle_denominator */
        SELECT COUNT(*)::bigint
        FROM audit_logs
        WHERE action_code = $1
          AND created_at >= $2
          AND created_at < $3
        """,
        _CODE_AI_CALL_STARTED,
        window_start,
        window_end,
    )
    return int(val or 0)


async def _fetch_count_by_code(
    conn, action_code: str, window_start: datetime, window_end: datetime
) -> int:
    val = await conn.fetchval(
        """/* sql_id: aggregate_principle_action_count */
        SELECT COUNT(*)::bigint
        FROM audit_logs
        WHERE action_code = $1
          AND created_at >= $2
          AND created_at < $3
        """,
        action_code,
        window_start,
        window_end,
    )
    return int(val or 0)


def _fetch_faithfulness(window_start: datetime, window_end: datetime) -> tuple[float | None, int]:
    """Return (mean_score, sample_n) from tests/test_rag_golden.py cumulative log if available."""
    golden_log = PROJECT_ROOT / ".omx" / "reports" / "verification" / "rag_golden_cumulative.json"
    if not golden_log.exists():
        return None, 0
    try:
        payload = json.loads(golden_log.read_text(encoding="utf-8"))
        scores = payload.get("scores", [])
        if not scores:
            return None, 0
        mean_score = sum(scores) / len(scores)
        return round(mean_score, 4), len(scores)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, 0


async def _compute_metric(
    conn,
    principle: str,
    metric: str,
    window_start: datetime,
    window_end: datetime,
    denominator: int,
) -> dict:
    """Compute a single metric and return the output JSON dict."""
    now = _now_utc()
    expires = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_path = MEASUREMENTS_DIR / f"{principle}_{metric}.json"

    value: float | None = None
    sample_n: int = 0
    p95: float | None = None

    if metric == "fail_closed_rate":
        count = await _fetch_count_by_code(
            conn, _CODE_AI_FAIL_CLOSED, window_start, window_end
        )
        sample_n = count
        value = round(count / denominator, 6) if denominator > 0 else 0.0

    elif metric == "injection_detected_rate":
        count = await _fetch_count_by_code(
            conn, _CODE_INJECTION_DETECTED, window_start, window_end
        )
        sample_n = count
        value = round(count / denominator, 6) if denominator > 0 else 0.0

    elif metric == "dual_llm_disagreement_rate":
        count = await _fetch_count_by_code(
            conn, _CODE_DUAL_LLM_DISAGREEMENT, window_start, window_end
        )
        sample_n = count
        value = round(count / denominator, 6) if denominator > 0 else 0.0

    elif metric == "pii_false_negative_rate":
        # FIX: 'ai_pii_false_negative' is registered in NONE of the three canonical
        # sources (V*.sql audit_action_codes / core.audit CANONICAL / OBS-02) and is
        # emitted by no router or service, so its count is structurally always 0.
        # Returning 0.0 would fabricate a "clean" privacy/fairness signal for a value
        # that is never measured. Emit an explicit PENDING_MEASUREMENT record instead.
        # denominator/freshness fields are preserved so the composite gate in
        # verify_total_product_readiness (keys on denominator+freshness, not value) works.
        return {
            "principle_id": principle,
            "metric": metric,
            "value": None,
            "status": "PENDING_MEASUREMENT",
            "p95": None,
            "sample_n": 0,
            "denominator_source": "audit_logs.AI_CALL_STARTED",
            "denominator": denominator,
            "last_measured_at": now,
            "expires_at": expires,
            "source_path": str(out_path.relative_to(PROJECT_ROOT)),
            "note": (
                "action_code 'ai_pii_false_negative' is not registered in "
                "V*.sql / core.audit CANONICAL / OBS-02 and is emitted by no router; "
                "pii_false_negative_rate is not measurable until the code is "
                "registered and emitted."
            ),
        }

    elif metric == "faithfulness":
        faith_val, faith_n = _fetch_faithfulness(window_start, window_end)
        value = faith_val if faith_val is not None else 0.0
        sample_n = faith_n

    return {
        "principle_id": principle,
        "metric": metric,
        "value": value,
        "p95": p95,
        "sample_n": sample_n,
        "denominator_source": "audit_logs.AI_CALL_STARTED",
        "denominator": denominator,
        "last_measured_at": now,
        "expires_at": expires,
        "source_path": str(out_path.relative_to(PROJECT_ROOT)),
    }


async def _collect_async(
    db_url: str,
    window_start: datetime,
    window_end: datetime,
    dry_run: bool,
) -> tuple[int, dict]:
    """Connect, run every query, and close — all on ONE event loop.

    Cross-loop fix: the asyncpg connection is created, used, and closed entirely
    within this single coroutine (driven by one asyncio.run in run()), so the
    connection is never accessed from a different / already-closed loop.
    Returns (exit_code, summary_dict).
    """
    import asyncpg  # type: ignore[import]

    window = {
        "start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    try:
        conn = await asyncpg.connect(db_url, timeout=15)
    except Exception as exc:  # noqa: BLE001
        return 3, {
            "status": "failed",
            "passed": False,
            "error": f"DB connection failed: {str(exc)[:300]}",
        }

    try:
        if dry_run:
            return 0, {
                "status": "passed",
                "passed": True,
                "dry_run": True,
                "window": window,
                "note": "DB connectivity verified; no files written in dry-run mode",
            }

        denominator = await _fetch_denominator(conn, window_start, window_end)
        MEASUREMENTS_DIR.mkdir(parents=True, exist_ok=True)

        any_failed = False
        results: list[dict] = []
        for principle in PRINCIPLES:
            for metric in PRINCIPLE_METRICS.get(principle, ()):
                try:
                    record = await _compute_metric(
                        conn, principle, metric, window_start, window_end, denominator
                    )
                    out_path = PROJECT_ROOT / record["source_path"]
                    out_path.write_text(
                        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    results.append({
                        "principle": principle,
                        "metric": metric,
                        "status": record.get("status", "written"),
                        "value": record["value"],
                    })
                except Exception as exc:  # noqa: BLE001
                    any_failed = True
                    results.append({
                        "principle": principle,
                        "metric": metric,
                        "status": "error",
                        "error": str(exc)[:200],
                    })

        summary = {
            "status": "failed" if any_failed else "passed",
            "passed": not any_failed,
            "window": window,
            "denominator": denominator,
            "denominator_source": "audit_logs.AI_CALL_STARTED",
            "results": results,
        }
        return (2 if any_failed else 0), summary
    finally:
        await conn.close()


def run(window_str: str, *, dry_run: bool = False) -> int:
    """Main execution: connect, compute metrics, write files. Returns exit code."""
    try:
        window_start, window_end = _parse_window(window_str)
    except ValueError as exc:
        print(json.dumps({"status": "failed", "passed": False, "error": str(exc)}), file=sys.stderr)
        return 3

    try:
        db_url = _get_db_url()
    except RuntimeError as exc:
        print(json.dumps({"status": "failed", "passed": False, "error": str(exc)}), file=sys.stderr)
        return 3

    try:
        import asyncpg  # type: ignore[import]  # noqa: F401
    except ImportError:
        msg = "asyncpg not installed; cannot connect to database"
        print(json.dumps({"status": "failed", "passed": False, "error": msg}), file=sys.stderr)
        return 3

    import asyncio

    exit_code, summary = asyncio.run(
        _collect_async(db_url, window_start, window_end, dry_run)
    )
    if exit_code == 3:
        print(json.dumps(summary), file=sys.stderr)
    else:
        print(json.dumps(summary, ensure_ascii=False))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window",
        required=True,
        metavar="YYYY-MM-DD",
        help="UTC calendar-day window for metrics aggregation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate args and DB connectivity without writing output files",
    )
    args = parser.parse_args(argv)
    return run(args.window, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
