#!/usr/bin/env python
"""P2-10 — non-RAG dispatcher faithfulness baseline.

The RAGAS baseline (scripts/wave_g_ragas.py) samples only citation-bearing RAG
traces. The single/dual-LLM dispatchers (portfolio_analysis, consultation_briefing,
nba_script) carry the deterministic faithfulness gate
(services/ai/output_quality.assess_faithfulness) on every generation, but had no
aggregated baseline. This recomputes that gate over the dispatchers' persisted
ai_outputs (the PII-safe ``_model_input`` grounding vs the output prose) and
aggregates per dispatcher: scored count, passed count, ungrounded-figures-flagged
count, missing-disclosure count.

It scores only rows that carry ``_model_input`` (the grounding the gate needs);
rows without it are counted as ``skipped_no_model_input``, NOT silently dropped.
The N>=30 target is a goal — the actual scored N reflects accumulated graded
traces and is printed explicitly so a thin sample is never read as a full
baseline. The ungrounded_figures substring false-negative ceiling is recorded in
the summary (a fabricated figure whose digits coincide with a grounding substring
is not flagged).

Usage:
  /opt/conda/envs/wm_env/bin/python scripts/wave_g_nonrag_faithfulness_baseline.py --n 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=True)

from apps.api.harness.services.ai.output_quality import assess_faithfulness  # noqa: E402

OUT_DIR = PROJECT_ROOT / "audit-out" / "stage-3" / "llm"
SUMMARY_PATH = OUT_DIR / "nonrag-faithfulness-baseline.json"

# In-product require_disclosure (portfolio_analysis.py / consultation_briefing.py /
# nba_script.py): all True, each appending the carried data_quality_notice to the
# assessed text — replicated here so the baseline mirrors the live gate (P2-5).
DISPATCHERS = ("portfolio_analysis", "consultation_briefing", "nba_script")


def _output_text(agent_id: str, oj: dict) -> str:
    """The banker-facing prose each dispatcher's in-product gate assesses."""
    if agent_id == "portfolio_analysis":
        return "\n".join([str(oj.get("summary", "")), str(oj.get("drift_analysis", ""))])
    if agent_id == "consultation_briefing":
        return "\n".join(
            [
                str(oj.get("customer_context_summary", "")),
                str(oj.get("portfolio_highlights", "")),
                str(oj.get("risk_notes", "")),
            ]
        )
    if agent_id == "nba_script":
        keys = ("opening_line", "key_message", "product_discussion_angle", "closing")
        return "\n".join(str(oj.get(k, "")) for k in keys)
    return ""


def _fetch(agent_id: str, n: int) -> list[dict]:
    dsn = os.environ["DATABASE_URL"]
    sql = (
        "SELECT id, agent_id, output_json FROM ai_outputs "
        "WHERE agent_id = %s AND output_json IS NOT NULL "
        "ORDER BY generated_at DESC LIMIT %s"
    )
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, (agent_id, n))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="target traces per dispatcher")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    per: dict[str, dict] = {}
    for agent_id in DISPATCHERS:
        rows = _fetch(agent_id, args.n)
        scored = passed = ungrounded = missing_disc = skipped = 0
        for row in rows:
            oj = row["output_json"] or {}
            model_input = oj.get("_model_input")
            if not isinstance(model_input, dict):
                skipped += 1
                continue
            notice = str(oj.get("data_quality_notice", ""))
            text = _output_text(agent_id, oj)
            assessed = text + ("\n" + notice if notice else "")
            faithfulness = assess_faithfulness(
                output_text=assessed, model_input=model_input, require_disclosure=True
            )
            scored += 1
            passed += int(bool(faithfulness["passed"]))
            ungrounded += int(bool(faithfulness["ungrounded_figures"]))
            missing_disc += int("MISSING_DATA_QUALITY_DISCLOSURE" in faithfulness["flags"])
        per[agent_id] = {
            "available_rows": len(rows),
            "scored": scored,
            "skipped_no_model_input": skipped,
            "passed": passed,
            "ungrounded_figures_flagged": ungrounded,
            "missing_disclosure_flagged": missing_disc,
            "meets_target_n": scored >= args.n,
        }
        if scored < args.n:
            print(
                f"[baseline] {agent_id}: scored {scored} < target {args.n} "
                f"(available {len(rows)}, skipped-no-input {skipped}) — "
                "thin sample, NOT a full baseline",
                flush=True,
            )

    summary = {
        "metric": "deterministic_faithfulness_v1",
        "target_n_per_dispatcher": args.n,
        "ungrounded_figures_caveat": (
            "substring match — known false-negative ceiling: a fabricated figure "
            "whose digits coincide with a grounding substring is NOT flagged "
            "(services/ai/output_quality.py:ungrounded_figures)"
        ),
        "per_dispatcher": per,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[baseline] summary -> {SUMMARY_PATH}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
