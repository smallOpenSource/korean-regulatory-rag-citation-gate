#!/usr/bin/env python
"""Wave G (G3) — Patronus Lynx 8B grounding scorer.

Mirrors scripts/wave_g_deepeval.py + scripts/wave_g_ragas.py shape:
same ai_outputs source, same per-trace JSON + aggregate summary file
layout. The distinguishing path is the **model** — Patronus Lynx is a
fine-tune of Llama-3 8B specifically trained to detect ungrounded
claims in RAG outputs, run locally via HuggingFace transformers.

Threshold (ADR-009 §dim-9-extension target):
  - grounding_score >= 0.85 — the model emits a [0, 1] grounding
    probability; the threshold can be re-tuned after the first live
    distribution lands.

Environment constraint (2026-05-22):
  Lynx 8B in fp16 = ~16GB RAM, fp32 = ~32GB. The wmah dev host has
  ~12GB free RAM and no CUDA GPU; the model cannot load in this env
  even after transformers + torch are installed. To exercise this
  script, run on a host with either:
    - GPU + CUDA (any modern Ampere/Hopper card with >=16GB VRAM)
    - CPU host with >=24GB free RAM (extremely slow inference)
  Alternatively, route through a remote inference endpoint (HF
  Inference Endpoints, vLLM server, etc.) and adapt the client to
  speak HTTP — the prompt + scoring logic stays unchanged.

Usage:
  python scripts/wave_g_lynx.py --n 3 --pilot
  python scripts/wave_g_lynx.py --n 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

OUT_DIR = PROJECT_ROOT / "audit-out" / "stage-3" / "llm" / "lynx"
SUMMARY_PATH = PROJECT_ROOT / "audit-out" / "stage-3" / "llm" / "lynx-summary.json"

GROUNDING_MIN = 0.85
DEFAULT_MODEL = "PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct"


PROMPT_TEMPLATE = """Given the following CONTEXT and ANSWER, determine if the ANSWER is grounded in the CONTEXT.

Respond with a JSON object: {{"grounded": true|false, "score": <0.0-1.0>, "reason": "<one sentence>"}}.

CONTEXT:
{context}

ANSWER:
{answer}
"""


class LynxClient:
    """Wraps the transformers AutoModelForCausalLM + tokenizer load."""

    def __init__(self, model_id: str = DEFAULT_MODEL, device: str | None = None):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        self.model_id = model_id
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        dtype = torch.float16 if device == "cuda" else torch.float32
        print(f"[wave_g_lynx] loading {model_id} on {device}...", flush=True)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map=device,
            low_cpu_mem_usage=True,
        )
        # Switch to inference mode (transformers model method, not Python eval).
        self.model.requires_grad_(False)

    def score(self, context: list[str], answer: str) -> dict:
        prompt = PROMPT_TEMPLATE.format(context="\n\n".join(context), answer=answer)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=200,
            do_sample=False,
            temperature=1.0,
        )
        gen = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
        try:
            return json.loads(gen.strip())
        except json.JSONDecodeError:
            return {"grounded": None, "score": None, "reason": gen.strip()[:200]}


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


def _coerce_score(x) -> float | None:
    # Lynx emits an untrusted JSON blob; score may arrive as a string like
    # "0.9" or a non-numeric token. Coerce to float defensively so one bad
    # trace cannot abort the whole sweep (summary write + all records lost).
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def extract_answer_and_context(row: dict) -> tuple[str, list[str]]:
    out = row["output_json"] or {}
    answer = (out.get("answer") or "").strip()
    citations = row["citations_json"] or []
    chunks = [(c.get("quote") or "").strip() for c in citations if c.get("quote")]
    return answer, [c for c in chunks if c]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        client = LynxClient(model_id=args.model, device=args.device)
    except Exception as exc:  # noqa: BLE001
        print(f"[wave_g_lynx] model load failed: {type(exc).__name__}: {exc}", flush=True)
        summary = {
            "n_total": 0,
            "model_load_error": f"{type(exc).__name__}: {exc}",
            "env_constraint": "Lynx 8B needs >=16GB RAM (fp16) or >=24GB RAM (fp32); wmah dev host insufficient",
            "model": args.model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    rows = fetch_traces(args.n)
    print(f"[wave_g_lynx] got {len(rows)} traces", flush=True)

    records = []
    for i, row in enumerate(rows, 1):
        trace_id = str(row["id"])
        answer, context = extract_answer_and_context(row)
        if not answer or not context:
            continue
        print(f"[{i}/{len(rows)}] {trace_id[:8]} scoring...", flush=True)
        try:
            verdict = client.score(context, answer)
        except Exception as exc:  # noqa: BLE001
            record = {
                "trace_id": trace_id,
                "grounded": None,
                "score": None,
                "score_pass": None,
                "reason": None,
                "score_error": f"{type(exc).__name__}: {exc}",
            }
            records.append(record)
            (OUT_DIR / f"trace-{trace_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2)
            )
            continue
        sc = _coerce_score(verdict.get("score"))
        record = {
            "trace_id": trace_id,
            "grounded": verdict.get("grounded"),
            "score": sc,
            "score_pass": (sc >= GROUNDING_MIN) if sc is not None else None,
            "reason": verdict.get("reason"),
        }
        records.append(record)
        (OUT_DIR / f"trace-{trace_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))

    pass_count = sum(1 for r in records if r.get("score_pass") is True)
    scored = sum(1 for r in records if r.get("score") is not None)
    mean = round(sum(r["score"] for r in records if r.get("score") is not None) / scored, 4) if scored else None
    summary = {
        "n_total": len(records),
        "n_scored": scored,
        "n_pass": pass_count,
        "mean_score": mean,
        "threshold_grounding_min": GROUNDING_MIN,
        "pilot": bool(args.pilot),
        "model": args.model,
        "device": client.device,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
