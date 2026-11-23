#!/usr/bin/env python
"""Wave G (G2) — DeepEval batch faithfulness + hallucination scorer.

Reads ai_outputs rows with paired output_json.answer + citations_json[].quote,
runs deepeval.FaithfulnessMetric + deepeval.HallucinationMetric against Azure
OpenAI (per .env AZURE_OPENAI_* vars), and emits:

  - audit-out/stage-3/llm/deepeval/trace-<id>.json (per-trace)
  - audit-out/stage-3/llm/deepeval-summary.json (aggregate)

Thresholds (ADR-009 §dim-9-extension target):
  - faithfulness >= 0.85 (FaithfulnessMetric measures alignment to context)
  - hallucination <= 0.10 (HallucinationMetric measures contradictions)

Per [[adr-spec-sot-verification]]: thresholds are bound here and propagated
to ADR-009 only after the first successful run produces actual numbers.

Usage:
  python scripts/wave_g_deepeval.py --n 3 --pilot   # smoke pilot
  python scripts/wave_g_deepeval.py --n 30          # full run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 정규 로더는 HARNESS_ENV_FILE 테스트 오버레이를 존중하고
# assert_critical_env_override stale-OS-env 가드를 적용한다. 셸에 stale Azure
# 엔드포인트(<stale-azure-resource>)가 남아 있어도 canonical <active-azure-resource>로 정정된다.
from apps.api.harness.core.config import default_env_path, load_env_file  # noqa: E402

load_env_file(default_env_path())

OUT_DIR = PROJECT_ROOT / "audit-out" / "stage-3" / "llm" / "deepeval"
SUMMARY_PATH = PROJECT_ROOT / "audit-out" / "stage-3" / "llm" / "deepeval-summary.json"

FAITHFULNESS_MIN = 0.85
HALLUCINATION_MAX = 0.10


def build_azure_model():
    from deepeval.models import AzureOpenAIModel

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_GPT5_MINI_DEPLOYMENT") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

    # DeepEval AzureOpenAIModel maps base_url -> openai.AzureOpenAI(azure_endpoint=...),
    # which expects the bare account endpoint (no /openai/deployments/... suffix).
    return AzureOpenAIModel(
        model=deployment,
        deployment_name=deployment,
        api_key=api_key,
        base_url=endpoint,
        api_version=api_version,
    ), {"endpoint": endpoint, "deployment": deployment, "api_version": api_version}


def fetch_traces(n: int) -> list[dict]:
    dsn = os.environ["DATABASE_URL"]
    sql = """
        SELECT id, agent_id, resource_type, output_json, citations_json
        FROM ai_outputs
        WHERE output_json IS NOT NULL
          AND citations_json IS NOT NULL
          AND jsonb_array_length(citations_json) > 0
        ORDER BY created_at DESC
        LIMIT %s
    """
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, (n,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def extract_answer_and_context(row: dict) -> tuple[str, list[str]]:
    out = row["output_json"] or {}
    answer = (out.get("answer") or "").strip()
    citations = row["citations_json"] or []
    chunks = [(c.get("quote") or "").strip() for c in citations if c.get("quote")]
    return answer, [c for c in chunks if c]


def score_one(metrics: dict, answer: str, context: list[str], trace_id: str) -> dict:
    from deepeval.test_case import LLMTestCase

    faith = metrics["faithfulness"]
    hallu = metrics["hallucination"]

    tc_faith = LLMTestCase(input="", actual_output=answer, retrieval_context=context)
    tc_hallu = LLMTestCase(input="", actual_output=answer, context=context)

    record: dict = {"trace_id": trace_id, "answer_len": len(answer), "context_chunks": len(context)}

    try:
        faith.measure(tc_faith)
        record["faithfulness_score"] = float(faith.score)
        record["faithfulness_reason"] = getattr(faith, "reason", None)
        record["faithfulness_pass"] = float(faith.score) >= FAITHFULNESS_MIN
    except Exception as exc:  # noqa: BLE001
        record["faithfulness_error"] = f"{type(exc).__name__}: {exc}"

    try:
        hallu.measure(tc_hallu)
        record["hallucination_score"] = float(hallu.score)
        record["hallucination_reason"] = getattr(hallu, "reason", None)
        record["hallucination_pass"] = float(hallu.score) <= HALLUCINATION_MAX
    except Exception as exc:  # noqa: BLE001
        record["hallucination_error"] = f"{type(exc).__name__}: {exc}"

    return record


def aggregate(records: list[dict]) -> dict:
    def mean(key: str) -> float | None:
        vals = [r[key] for r in records if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 4) if vals else None

    return {
        "n_total": len(records),
        "n_faithfulness_scored": sum(1 for r in records if "faithfulness_score" in r),
        "n_hallucination_scored": sum(1 for r in records if "hallucination_score" in r),
        "n_faithfulness_pass": sum(1 for r in records if r.get("faithfulness_pass") is True),
        "n_hallucination_pass": sum(1 for r in records if r.get("hallucination_pass") is True),
        "n_both_pass": sum(
            1 for r in records if r.get("faithfulness_pass") and r.get("hallucination_pass")
        ),
        "mean_faithfulness": mean("faithfulness_score"),
        "mean_hallucination": mean("hallucination_score"),
        "threshold_faithfulness_min": FAITHFULNESS_MIN,
        "threshold_hallucination_max": HALLUCINATION_MAX,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="number of traces (default 30)")
    ap.add_argument("--pilot", action="store_true", help="pilot run; tags summary")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[wave_g_deepeval] building Azure model...", flush=True)
    from deepeval.metrics import FaithfulnessMetric, HallucinationMetric

    model, model_meta = build_azure_model()
    metrics = {
        "faithfulness": FaithfulnessMetric(threshold=FAITHFULNESS_MIN, model=model, async_mode=False),
        "hallucination": HallucinationMetric(threshold=HALLUCINATION_MAX, model=model, async_mode=False),
    }

    print(f"[wave_g_deepeval] fetching {args.n} traces...", flush=True)
    rows = fetch_traces(args.n)
    print(f"[wave_g_deepeval] got {len(rows)} traces", flush=True)

    records: list[dict] = []
    for i, row in enumerate(rows, 1):
        trace_id = str(row["id"])
        answer, context = extract_answer_and_context(row)
        if not answer or not context:
            print(f"[{i}/{len(rows)}] {trace_id[:8]} SKIP (no answer/context)", flush=True)
            continue
        print(f"[{i}/{len(rows)}] {trace_id[:8]} scoring...", flush=True)
        rec = score_one(metrics, answer, context, trace_id)
        records.append(rec)
        (OUT_DIR / f"trace-{trace_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        f = rec.get("faithfulness_score")
        h = rec.get("hallucination_score")
        print(f"  -> faithfulness={f} hallucination={h}", flush=True)

    summary = aggregate(records)
    summary["pilot"] = bool(args.pilot)
    summary["requested_n"] = args.n
    summary["model"] = model_meta
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[wave_g_deepeval] summary -> {SUMMARY_PATH}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
