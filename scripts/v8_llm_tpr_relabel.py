#!/usr/bin/env python
"""v8_llm_tpr_relabel.py — Stage 4 LLM-as-TPR re-label (사용자 명시 권한)

TPR (Third Party Reviewer) re-label 30 sample은 PRD §G11 + EDIT-12 conflict-of-interest
차단. 사용자가 직접 별도 OMC/Claude session 진입하는 것이 원래 spec.

사용자 명시 권한 2026-05-20 적용 — LLM이 다른 prompt strategy로 self-bias 부분 차단:
  - L2 critic은 BANNED pattern checklist 기반 평가
  - TPR re-label은 "first-principles" 평가 (BANNED list 미명시, 직접 한국어 자연성 판단)
  - 같은 LLM (gpt-5.5) 이지만 prompt difference가 evaluation 결과 차이를 만들 수 있음

LIMITATION:
  - Independence boundary 부분 위반 (다른 session 아님)
  - 사용자 panel TPR 도착 시 추가 verification 의무

Sample selection (DELTA-process):
  - 30 samples from calibration set (cal-071 ~ cal-100) — adversarial-leaning FAIL strata
  - 또는 cycle 1+2 visited spot-check 결과 disagreement 우선 sample

Output:
  .omc/state/v8-tpr-relabel-cycle-3.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LABELS_FILE = REPO_ROOT / ".omc/state/v8-calibration-labels.yaml"
ENV_FILE = REPO_ROOT / ".env"

# TPR-specific prompt — first-principles, no BANNED checklist
TPR_PROMPT = """당신은 독립 검토자입니다 (PB/WM 업무 화면 품질 평가).
이 텍스트가 한국 금융사 PB(Private Banker) 직원의 업무 화면에 표시되었을 때,
사용자(PB 직원)가 거부감 없이 자연스럽게 사용할 수 있는지 first-principles로 평가하세요.

평가는 "이 화면을 보고 PB가 즉시 사용할 수 있는가?" 단일 기준입니다.
PASS = 즉시 사용 가능 / FAIL = 어색하거나 혼란스러움.

이전 평가자의 결론과 무관하게 독립적으로 판단하세요.

평가 대상 텍스트:
---
{text}
---

JSON 응답: {{"label": "PASS"|"FAIL", "reason": "왜 그렇게 판단했는가 (간단히)"}}
"""


def load_env_var(key: str) -> str:
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def call_tpr(text: str) -> dict[str, Any]:
    from openai import AzureOpenAI  # type: ignore[import-untyped]
    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5")
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "당신은 독립 first-principles 검토자입니다. JSON만 응답하세요."},
            {"role": "user", "content": TPR_PROMPT.format(text=text)},
        ],
        max_completion_tokens=256,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "{}").strip()
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LLM-as-TPR re-label (gpt-5.5 first-principles)")
    p.add_argument("--sample-size", type=int, default=30)
    p.add_argument("--start", type=int, default=71, help="cal-NNN start (default 71 = adversarial-leaning)")
    args = p.parse_args(argv)

    # Load env
    for key in ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_VERSION",
                "AZURE_OPENAI_DEPLOYMENT_NAME"]:
        env_val = load_env_var(key)
        if env_val:
            os.environ[key] = env_val  # .env 강제 override (stale OS env 차단)

    if not LABELS_FILE.exists():
        print(json.dumps({"error": "v8-calibration-labels.yaml missing; run v8_llm_calibration_labeler first"}))
        return 2

    with LABELS_FILE.open() as fh:
        labels: dict[str, Any] = yaml.safe_load(fh)
    samples: list[dict[str, Any]] = labels.get("samples", [])
    # Select cal-{start} ~ cal-{start + sample_size - 1}
    target_samples = [s for s in samples
                       if int(s["sample_id"].split("-")[1]) >= args.start
                       and int(s["sample_id"].split("-")[1]) < args.start + args.sample_size]

    print(f"[TPR] re-labeling {len(target_samples)} samples (cal-{args.start:03d} ~)")

    disagreements = 0
    results: list[dict[str, Any]] = []
    for s in target_samples:
        original_label = s["ground_truth"]
        text = s.get("text_snippet", "")
        if not text:
            continue
        try:
            tpr_verdict = call_tpr(text)
            tpr_label = tpr_verdict.get("label", "PASS")
            disagree = (tpr_label != original_label)
            if disagree:
                disagreements += 1
            results.append({
                "sample_id": s["sample_id"],
                "original_label": original_label,
                "tpr_label": tpr_label,
                "disagree": disagree,
                "tpr_reason": tpr_verdict.get("reason", "")[:200],
            })
        except Exception as e:
            results.append({
                "sample_id": s["sample_id"],
                "error": str(e)[:200],
            })

    out_path = REPO_ROOT / ".omc/state/v8-tpr-relabel-cycle-3.yaml"
    output = {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reviewer": "llm_gpt-5.5_first_principles_prompt",
        "limitation_notice": (
            "TPR re-label by LLM (gpt-5.5) with first-principles prompt (vs L2 BANNED checklist prompt). "
            "Independence boundary 부분 위반 (다른 OMC session 아님). "
            "사용자 panel TPR 도착 시 추가 verification 의무."
        ),
        "prd_ref": "PRD §5.4.5 + DELTA-4/M1 + EDIT-12/G11 tpr_sample_size=30",
        "sample_size": len(results),
        "disagreement_count": disagreements,
        "disagreement_rate": round(disagreements / max(len(results), 1), 4),
        "samples": results,
    }
    out_path.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": True,
        "sample_size": len(results),
        "disagreement_count": disagreements,
        "disagreement_rate": output["disagreement_rate"],
        "output": str(out_path),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
