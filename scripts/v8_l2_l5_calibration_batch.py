#!/usr/bin/env python
"""v8_l2_l5_calibration_batch.py — Stage 3 cycle 2 framework deliverable (T106/T107 batch)

L_calibration false-negative rate measurement for cycle N.

Inputs:
  - .omc/state/v8-calibration-labels.yaml (사용자 panel ground truth — 100 cells,
    50 PASS + 50 FAIL). FAIL labels include defect_type (BANNED_PLACEHOLDER, etc.)
    Currently MISSING — calibration_labeler 100 cells run user side pending.
  - .omc/state/v8-calibration-candidates/cal-NNN.{png,json} (Stage 0 G0c-1 박제, 200 files)

Process (per cycle):
  1. Select calibration_eval_per_cycle=50 samples via deterministic rotation
     (DELTA-6/M3): cycle 1 → samples [0..49], cycle 2 → [50..99], cycle 3 → [0..49]
  2. For each sample, run L2 (text input) + L5 (vision input) via Azure dispatcher
  3. Compare critic verdict vs ground truth label
  4. Compute false-negative rate = (FAIL labeled but L2/L5 said PASS) / total FAIL
  5. Apply binomial proportion exact test (95% CI ±13.9% at n=50)
  6. PASS threshold: false-negative < 5% with 95% CI

Output:
  .omc/state/v8-l2-l5-calibration-result-cycle-N.yaml

Usage:
  AZURE_OPENAI_API_KEY=... v8_l2_l5_calibration_batch.py --cycle 2
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LABELS_FILE = REPO_ROOT / ".omc/state/v8-calibration-labels.yaml"
CANDIDATES_DIR = REPO_ROOT / ".omc/state/v8-calibration-candidates"
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from v8_detector_L2_korean_critic import evaluate_l2  # noqa: E402
from v8_detector_L5_visual_critic import evaluate_l5  # noqa: E402

CALIBRATION_EVAL_PER_CYCLE = 50
CALIBRATION_SET_SIZE = 100  # 50 PASS + 50 FAIL


def rotation_indices(cycle: int) -> tuple[int, int]:
    """DELTA-6/M3 deterministic rotation: cycle N → samples [(N-1)×50 mod 100, ...].

    cycle 1: [0, 49]; cycle 2: [50, 99]; cycle 3: [0, 49] (cycle reuses cycle 1).
    """
    start = ((cycle - 1) * CALIBRATION_EVAL_PER_CYCLE) % CALIBRATION_SET_SIZE
    end = start + CALIBRATION_EVAL_PER_CYCLE - 1
    return start, end


def binomial_ci_95(n_fail: int, n_total: int) -> tuple[float, float, float]:
    """Wilson 95% CI for false-negative proportion.

    Returns (point_estimate, lower_bound, upper_bound).
    At n=50, margin is ~±13.9% per PRD §13.1.
    """
    if n_total == 0:
        return 0.0, 0.0, 0.0
    p = n_fail / n_total
    z = 1.96
    denom = 1 + z * z / n_total
    center = (p + z * z / (2 * n_total)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n_total + z * z / (4 * n_total * n_total))) / denom
    return p, max(0.0, center - margin), min(1.0, center + margin)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L2/L5 calibration batch (cycle N)")
    p.add_argument("--cycle", type=int, required=True, help="cycle number 1-3")
    p.add_argument("--dry-run", action="store_true",
                   help="skeleton mode, no Azure API calls")
    p.add_argument("--output-dir", type=pathlib.Path,
                   default=REPO_ROOT / ".omc/state")
    args = p.parse_args(argv)

    if not LABELS_FILE.exists():
        print(json.dumps({
            "status": "PENDING-USER-CALIBRATION-LABELS",
            "labels_file": str(LABELS_FILE),
            "reason": (
                "사용자 calibration_labeler 100 cells (50 PASS + 50 FAIL) labeling "
                "pending. Run: /opt/conda/envs/wm_env/bin/python "
                "scripts/v8_calibration_labeler.py "
                "(3.3h CLI, resume-capable). 결과 v8-calibration-labels.yaml 도착 후 "
                "본 batch invoke 가능."
            ),
            "PRD_ref": "PRD §3.7.1 + DELTA-6/M3 + ADR-009 §Decision L_calibration",
        }, ensure_ascii=False, indent=2))
        return 2

    with LABELS_FILE.open() as fh:
        labels: dict[str, Any] = yaml.safe_load(fh)

    samples: list[dict[str, Any]] = labels.get("samples", [])
    if len(samples) != CALIBRATION_SET_SIZE:
        print(json.dumps({
            "status": "INVALID-CALIBRATION-SET",
            "expected": CALIBRATION_SET_SIZE,
            "got": len(samples),
        }))
        return 2

    start, end = rotation_indices(args.cycle)
    selected = samples[start:end + 1]
    print(f"[L2/L5 batch] cycle {args.cycle}: rotating samples [{start}..{end}] ({len(selected)} samples)")

    results: list[dict[str, Any]] = []
    n_fail_total = 0
    n_fail_detected = 0
    n_pass_total = 0
    n_pass_false_alarm = 0

    for sample in selected:
        sample_id = sample.get("sample_id")
        ground_truth = sample.get("ground_truth")  # "PASS" or "FAIL"
        text_snippet = sample.get("text_snippet", "")
        screenshot_rel = sample.get("screenshot_path", "")
        viewport = sample.get("viewport", "desktop_wide")
        screenshot_path = CANDIDATES_DIR / screenshot_rel if screenshot_rel else None

        l2_pass = True
        l5_pass = True
        if text_snippet:
            verdict = evaluate_l2(text_snippet, dry_run=args.dry_run)
            l2_pass = verdict.pass_
        if screenshot_path and screenshot_path.exists():
            verdict5 = evaluate_l5(screenshot_path, viewport, dry_run=args.dry_run)
            l5_pass = verdict5.pass_

        combined_pass = l2_pass and l5_pass

        # False-negative check: ground truth=FAIL but L2+L5 said PASS
        if ground_truth == "FAIL":
            n_fail_total += 1
            if not combined_pass:
                n_fail_detected += 1
        elif ground_truth == "PASS":
            n_pass_total += 1
            if not combined_pass:
                n_pass_false_alarm += 1

        results.append({
            "sample_id": sample_id,
            "ground_truth": ground_truth,
            "l2_pass": l2_pass,
            "l5_pass": l5_pass,
            "combined_pass": combined_pass,
            "correct": (combined_pass == (ground_truth == "PASS")),
        })

    false_negative_count = n_fail_total - n_fail_detected
    false_neg_p, fn_lo, fn_hi = binomial_ci_95(false_negative_count, n_fail_total)
    pass_threshold_5pct = fn_hi < 0.05

    summary = {
        "cycle": args.cycle,
        "rotation_range": [start, end],
        "samples_evaluated": len(selected),
        "fail_labeled_total": n_fail_total,
        "fail_detected_by_l2l5": n_fail_detected,
        "false_negative_count": false_negative_count,
        "false_negative_rate": round(false_neg_p, 4),
        "false_negative_ci_95_lower": round(fn_lo, 4),
        "false_negative_ci_95_upper": round(fn_hi, 4),
        "pass_threshold_5pct_with_95_ci": pass_threshold_5pct,
        "pass_labeled_total": n_pass_total,
        "pass_false_alarm_count": n_pass_false_alarm,
        "results": results,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"v8-l2-l5-calibration-result-cycle-{args.cycle}.yaml"
    with out_path.open("w") as fh:
        yaml.safe_dump(summary, fh, allow_unicode=True, sort_keys=False)

    # Print summary
    print(json.dumps({
        "status": "complete",
        "cycle": args.cycle,
        "false_negative_rate": summary["false_negative_rate"],
        "false_negative_ci_95": [summary["false_negative_ci_95_lower"],
                                  summary["false_negative_ci_95_upper"]],
        "pass_threshold_5pct": pass_threshold_5pct,
        "output": str(out_path),
    }, ensure_ascii=False, indent=2))
    return 0 if pass_threshold_5pct else 1


if __name__ == "__main__":
    sys.exit(main())
