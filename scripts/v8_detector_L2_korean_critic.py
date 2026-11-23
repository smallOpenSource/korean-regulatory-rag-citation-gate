#!/usr/bin/env python
"""v8_detector_L2_korean_critic.py — Stage 2 G2 deliverable (T106)

L2 한국어 자연성 LLM critic. Opus-4-7 text input.
Calibration rotation: calibration_eval_per_cycle=50 samples (DELTA-6/M3).
Goal: false-negative rate < 5% with 95% CI (binomial proportion exact test,
margin ±13.9%).

NOTE: Stage 2 framework deliverable. Live Anthropic API call requires
ANTHROPIC_API_KEY env var. Without key, returns dry-run skeleton.

Rate limit awareness: Anthropic batch_request endpoint preferred for cycle 1
50 sample batch. Per-call retry with exponential backoff.

Cache: key = sha256(text), value = critic verdict JSON. Cycle 1 50 sample
results cached at .omc/state/v8-l2-cache/{sha}.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
L2_CACHE_DIR = REPO_ROOT / ".omc/state/v8-l2-cache"
DEFAULT_MODEL = os.environ.get("V8_L2_MODEL", "claude-opus-4-7")

L2_PROMPT_TEMPLATE = """당신은 한국어 자연성 검토자입니다. 다음 한국어 텍스트가 PB(Private Banker) 화면에 노출되었을 때 자연스러운지 평가하세요.

평가 기준:
1. 한국어 존댓말 (반말 금지)
2. 전문 금융 어휘 적절성 (영문 내부 식별자 노출 금지)
3. placeholder/empty-state 텍스트가 안정적인지 (예: "응답을 기다리는 중" 영구 노출 금지)
4. 호칭 일관성 (PB님 / 고객님 — "PB씨" 같은 비격식 표현 금지)
5. timestamp/금액 format 자연성 (마이크로초/UTC offset 노출 금지)

평가 대상 텍스트:
---
{text}
---

다음 JSON 형식으로만 응답:
{{"pass": true|false, "issues": ["issue1", "issue2", ...], "confidence": 0.0~1.0, "reason": "간단 사유"}}
"""


@dataclass
class L2Verdict:
    pass_: bool
    issues: list[str]
    confidence: float
    reason: str
    cached: bool = False
    model: str = DEFAULT_MODEL


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def cache_get(sha: str) -> dict[str, Any] | None:
    path = L2_CACHE_DIR / f"{sha}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_put(sha: str, verdict: dict[str, Any]) -> None:
    L2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (L2_CACHE_DIR / f"{sha}.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def call_azure_openai_api(text: str) -> dict[str, Any]:
    """Live Azure OpenAI API call (gpt-5.5 default).

    Reuses wmah dispatcher pattern (apps/api/harness/services/house_view.py:139).
    Requires: AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT env vars.
    """
    try:
        from openai import AzureOpenAI  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("openai package missing. Required for L2 Azure critic.") from e

    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip()
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5").strip()
    if not api_key or not endpoint:
        raise RuntimeError(
            "AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT required for L2 Azure critic"
        )

    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )
    prompt = L2_PROMPT_TEMPLATE.format(text=text)
    delay = 1.0
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": "당신은 한국어 자연성 검토자입니다. JSON만 응답하세요."},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=512,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "{}").strip()
            return json.loads(raw)
        except Exception as e:
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"L2 Azure API call failed after 5 attempts: {e}") from e
    raise RuntimeError("unreachable")


def evaluate_l2(text: str, dry_run: bool = False) -> L2Verdict:
    sha = text_hash(text)
    cached = cache_get(sha)
    if cached is not None:
        return L2Verdict(
            pass_=cached.get("pass", False),
            issues=cached.get("issues", []),
            confidence=cached.get("confidence", 0.0),
            reason=cached.get("reason", ""),
            cached=True,
            model=cached.get("model", DEFAULT_MODEL),
        )
    if dry_run:
        return L2Verdict(
            pass_=True,
            issues=[],
            confidence=0.0,
            reason="dry-run (no API call)",
            cached=False,
            model="dry-run",
        )
    result = call_azure_openai_api(text)
    model_used = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5")
    result["model"] = model_used
    cache_put(sha, result)
    return L2Verdict(
        # fail-closed: a malformed/truncated verdict missing "pass" is a defect to
        # surface for human review, not a silent PASS (fail-closed posture, #4-A audit).
        pass_=result.get("pass", False),
        issues=result.get("issues", []),
        confidence=result.get("confidence", 0.0),
        reason=result.get("reason", ""),
        cached=False,
        model=model_used,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L2 Korean naturalness LLM critic")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--text-file", type=pathlib.Path)
    src.add_argument("--text", type=str)
    src.add_argument("--stdin", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="skeleton mode, no API call (returns pass=true)")
    args = p.parse_args(argv)

    if args.text_file is not None:
        text = args.text_file.read_text(encoding="utf-8")
    elif args.stdin:
        text = sys.stdin.read()
    else:
        text = args.text

    verdict = evaluate_l2(text, dry_run=args.dry_run)
    out: dict[str, Any] = {
        "pass": verdict.pass_,
        "issues": verdict.issues,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        "cached": verdict.cached,
        "model": verdict.model,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if verdict.pass_ else 1


if __name__ == "__main__":
    sys.exit(main())
