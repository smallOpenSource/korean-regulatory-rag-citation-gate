#!/usr/bin/env python3
"""WMAH Audit Stage 2 Lane 3 — Hallucination detector wrapper.

Strategy:
1. Prefer Lynx (Patronus AI) OSS model when available locally.
2. Fall back to LLM-as-judge (Azure GPT-4) when Lynx isn't installed.

Both backends emit a fast hallucination score in [0.0, 1.0] (higher = more
hallucinated) per (context, response) pair.

Output:
    audit-out/llm/hallucination-scores.csv with columns:
        agent_id, sample_id, score, backend, judged_at_utc, notes

References:
- Lynx: https://huggingface.co/PatronusAI/Patronus-Lynx-70B-Instruct
- Caveats: memory feedback-llm-as-evaluator-limitation — even Lynx/judge are
  proxies; pair with services/ai/faithfulness.py rule-based check.

Usage::

    python eval/llm/hallucination-detector.py \
        --input audit-out/stage-3/llm/rag-traces.jsonl \
        --output audit-out/llm/hallucination-scores.csv \
        [--backend auto|lynx|judge] \
        [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "audit-out" / "stage-3" / "llm" / "rag-traces.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "audit-out" / "llm" / "hallucination-scores.csv"


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------


def _lynx_available() -> bool:
    try:
        import transformers  # noqa: F401
        # Lynx weights cached?
        cache_marker = os.environ.get("LYNX_MODEL_PATH", "")
        return bool(cache_marker) and Path(cache_marker).exists()
    except Exception:
        return False


def _judge_available() -> bool:
    return bool(os.environ.get("AZURE_OPENAI_API_KEY")) and bool(
        os.environ.get("AZURE_OPENAI_ENDPOINT")
    )


def select_backend(requested: str) -> str:
    if requested == "lynx":
        if not _lynx_available():
            raise SystemExit(
                "FATAL: --backend lynx requested but Lynx weights not "
                "found (set LYNX_MODEL_PATH or install transformers)."
            )
        return "lynx"
    if requested == "judge":
        if not _judge_available():
            raise SystemExit(
                "FATAL: --backend judge requires AZURE_OPENAI_API_KEY + "
                "AZURE_OPENAI_ENDPOINT env vars."
            )
        return "judge"
    if requested == "auto":
        if _lynx_available():
            return "lynx"
        if _judge_available():
            return "judge"
        return "stub"  # offline deterministic mode
    raise SystemExit(f"unknown backend: {requested!r}")


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------


def _stub_score(context: str, response: str) -> float:
    """Deterministic offline scorer for CI/dry-run.

    Score = (sha256 first byte) / 255  -- uniform distribution by hash.
    """
    digest = hashlib.sha256(
        (context + "||" + response).encode("utf-8")
    ).digest()
    return digest[0] / 255.0


def _lynx_score(context: str, response: str) -> float:  # pragma: no cover
    """Lynx-Instruct score: 1 - faithfulness_prob."""
    # Lazy import; Stage 3 wires this when Lynx weights land.
    from transformers import AutoTokenizer, AutoModelForCausalLM  # type: ignore
    import torch  # type: ignore

    model_path = os.environ["LYNX_MODEL_PATH"]
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(model_path)

    prompt = (
        "Given the CONTEXT and the RESPONSE, judge whether every claim in "
        "RESPONSE is supported by CONTEXT. Reply with a single float in "
        "[0.0, 1.0] where 1.0 means fully supported, 0.0 fully hallucinated."
        f"\n\nCONTEXT:\n{context}\n\nRESPONSE:\n{response}\n\nSCORE:"
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=8)
    text = tokenizer.decode(out[0], skip_special_tokens=True)
    try:
        faith = float(text.strip().split()[-1])
    except Exception:
        faith = 0.5
    return max(0.0, min(1.0, 1.0 - faith))


def _judge_score(context: str, response: str) -> float:  # pragma: no cover
    """gpt-4 LLM-as-judge fallback."""
    # Lazy import — keep base CLI runnable in air-gapped CI.
    from openai import AzureOpenAI  # type: ignore

    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-02-15-preview",
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    sys_msg = (
        "당신은 한국어 자산관리(PB) 도메인의 hallucination 평가자입니다. "
        "주어진 CONTEXT와 RESPONSE를 비교해, RESPONSE의 각 claim이 CONTEXT로부터 "
        "추론 가능한지 판정하고, hallucination_score를 0.0(완전 정합)~1.0(완전 환각) "
        "사이의 float 한 개로만 응답하세요."
    )
    user_msg = f"CONTEXT:\n{context}\n\nRESPONSE:\n{response}"
    rsp = client.chat.completions.create(
        model=os.environ.get("AZURE_GPT4_DEPLOYMENT", "gpt-4-eval"),
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=8,
    )
    text = (rsp.choices[0].message.content or "").strip()
    try:
        return max(0.0, min(1.0, float(text.split()[0])))
    except Exception:
        return 0.5


def score_one(backend: str, context: str, response: str) -> float:
    if backend == "stub":
        return _stub_score(context, response)
    if backend == "lynx":
        return _lynx_score(context, response)
    if backend == "judge":
        return _judge_score(context, response)
    raise SystemExit(f"unknown backend: {backend!r}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return iter(())
    with path.open("r", encoding="utf-8") as fh:
        for ln, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                sys.stderr.write(
                    f"[hallucination-detector] line {ln}: skipped ({exc})\n"
                )


def run(
    input_path: Path,
    output_path: Path,
    backend: str,
    dry_run: bool,
) -> dict[str, Any]:
    effective_backend = "stub" if dry_run else select_backend(backend)
    rows_written = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "agent_id",
                "sample_id",
                "score",
                "backend",
                "judged_at_utc",
                "notes",
            ]
        )
        for row in iter_jsonl(input_path):
            agent_id = row.get("agent_id") or row.get("agent") or "unknown"
            sample_id = (
                row.get("sample_id")
                or row.get("id")
                or hashlib.sha256(
                    json.dumps(row, sort_keys=True, ensure_ascii=False).encode(
                        "utf-8"
                    )
                ).hexdigest()[:16]
            )
            context = row.get("context") or row.get("contexts")
            if isinstance(context, list):
                context = "\n---\n".join(context)
            response = row.get("answer") or row.get("response") or ""
            if not context or not response:
                continue
            score = score_one(effective_backend, str(context), str(response))
            writer.writerow(
                [
                    agent_id,
                    sample_id,
                    f"{score:.4f}",
                    effective_backend,
                    datetime.now(timezone.utc).isoformat(),
                    "ok",
                ]
            )
            rows_written += 1
    return {
        "rows_written": rows_written,
        "backend": effective_backend,
        "output": str(output_path),
        "input": str(input_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--backend",
        choices=["auto", "lynx", "judge", "stub"],
        default="auto",
        help="auto: prefer Lynx, fall back to judge, then stub.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force deterministic stub scorer.",
    )
    args = parser.parse_args(argv)

    summary = run(
        input_path=args.input,
        output_path=args.output,
        backend=args.backend,
        dry_run=args.dry_run,
    )
    sys.stdout.write(
        f"[hallucination-detector] backend={summary['backend']} "
        f"rows={summary['rows_written']} output={summary['output']}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
