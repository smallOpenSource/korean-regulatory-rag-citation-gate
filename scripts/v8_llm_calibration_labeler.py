#!/usr/bin/env python
"""v8_llm_calibration_labeler.py — Stage 4 LLM-as-labeler proxy (사용자 명시 권한)

Stage 0 G0c-1에서 calibration set 100 cells × `expected_pass` (synthetic
ground truth) 박제됨. 사용자 panel labeling을 LLM이 대체 — 이 script는
v8-calibration-candidates-index.yaml의 `expected_pass`를 PASS/FAIL labels로
변환하여 v8-calibration-labels.yaml 박제.

LIMITATION (PRD §G11 부분 위반, ADR-009 §Status framework_side termination 적용):
  - Ground truth = Stage 0 designer intent (synthetic), NOT 사용자 panel
  - L2 LLM critic이 같은 set에 대해 evaluate 시 self-consistency만 측정
  - 사용자 panel labeling 도착 시 추가 verification 의무

PRD §G0c-1 spec:
  - cal-001 ~ cal-050: 50 PASS (정상 cells, expected_pass=true)
  - cal-051 ~ cal-100: 50 FAIL (5 BANNED 패턴 의도적 포함, expected_pass=false)
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_FILE = REPO_ROOT / ".omc/state/v8-calibration-candidates-index.yaml"
OUTPUT_FILE = REPO_ROOT / ".omc/state/v8-calibration-labels.yaml"
CANDIDATES_DIR = REPO_ROOT / ".omc/state/v8-calibration-candidates"


def main() -> int:
    with INDEX_FILE.open() as fh:
        index: dict[str, Any] = yaml.safe_load(fh)
    cells: list[dict[str, Any]] = index.get("cells", [])
    if not cells:
        print(json.dumps({"error": "no cells in index"}))
        return 2

    samples: list[dict[str, Any]] = []
    for c in cells:
        cell_id = c["cell_id"]
        # Read text_snippet from cal-NNN.json (more complete than index summary)
        json_path = CANDIDATES_DIR / f"{cell_id}.json"
        full_text = c.get("visible_text_snippet", "")
        if json_path.exists():
            meta = json.loads(json_path.read_text(encoding="utf-8"))
            full_text = meta.get("visible_text_snippet", full_text)

        label = "PASS" if c.get("expected_pass") else "FAIL"
        samples.append({
            "sample_id": cell_id,
            "ground_truth": label,
            "defect_type": c.get("expected_reason") if label == "FAIL" else None,
            "reason": c.get("expected_reason") or "stage_0_designer_intent",
            "text_snippet": full_text[:1500],
            "screenshot_path": f"{cell_id}.png",
            "viewport": "desktop_wide",  # candidates use default
            "labeled_by": "stage_0_designer_intent_via_llm_labeler_proxy",
            "labeled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "route": c.get("route"),
            "role": c.get("role"),
        })

    pass_count = sum(1 for s in samples if s["ground_truth"] == "PASS")
    fail_count = sum(1 for s in samples if s["ground_truth"] == "FAIL")
    output = {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "labeler": "stage_0_g0c1_designer_intent_via_index",
        "limitation_notice": (
            "Ground truth labels derived from Stage 0 G0c-1 designer intent "
            "(synthetic, NOT 사용자 panel). 사용자 명시 권한 2026-05-20 적용 — "
            "ADR-009 §Status framework_side termination. 사용자 panel labeling "
            "도착 시 v8_calibration_labeler.py 통해 ground truth update + 재verify 의무."
        ),
        "prd_ref": "PRD §3.7.1 + DELTA-6/M3 + PRD §G0c-1 calibration set design",
        "total_samples": len(samples),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "samples": samples,
    }
    OUTPUT_FILE.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": True,
        "total_samples": len(samples),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "output": str(OUTPUT_FILE),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
