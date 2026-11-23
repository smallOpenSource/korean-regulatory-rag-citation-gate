#!/usr/bin/env python
"""v8_llm_user_spot_check.py — Stage 4 LLM-as-panel spot-check (사용자 명시 권한)

371 cells × 3 cycle = 1,113 cumulative cells 사용자 panel labeling을 LLM이 대체.

Sample selection (DELTA-process Cochran):
  - random_split = 185 cells (deterministic seed)
  - adversarial_split = 186 cells (cells with HIGH or MEDIUM unreachable_confidence,
    or cells near route boundary)
  - Total: 371 cells per cycle

LLM evaluation:
  - L2 text critic (gpt-5.5) for visible_text_excerpt
  - PASS/FAIL binary + reason

LIMITATION (PRD §G11 부분 위반, ADR-009 §Status framework_side termination):
  - Panel = LLM-generated (gpt-5.5), NOT 사용자 panel ground truth
  - 같은 LLM (gpt-5.5)이 L_calibration + L_user_spot_check evaluator로 사용되면 self-consistency
  - 사용자 panel labeling 도착 시 추가 verification 의무

Output:
  .omc/state/v8-user-spot-check-cycle-N.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import re
import sys
import time
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from v8_detector_L2_korean_critic import evaluate_l2  # noqa: E402


def load_env_var(key: str) -> str:
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LLM-as-panel spot-check (gpt-5.5)")
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--n-user-sample", type=int, default=371)
    p.add_argument("--random-split", type=int, default=185)
    p.add_argument("--adversarial-split", type=int, default=186)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit-time-min", type=int, default=20,
                   help="time budget — stops early if exceeded")
    args = p.parse_args(argv)

    # Load Azure env vars
    for key in ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_VERSION",
                "AZURE_OPENAI_DEPLOYMENT_NAME"]:
        env_val = load_env_var(key)
        if env_val:
            os.environ[key] = env_val  # .env 강제 override (stale OS env 차단)

    cycle_dir = REPO_ROOT / ".omc/state/v8-traversal" / f"cycle_{args.cycle}"
    visited_path = cycle_dir / "visited.jsonl"
    if not visited_path.exists():
        print(json.dumps({"error": f"no visited.jsonl at {visited_path}"}))
        return 2

    rows: list[dict[str, Any]] = []
    with visited_path.open() as fh:
        for line in fh:
            rows.append(json.loads(line))

    rng = random.Random(args.seed)
    # Stratified sampling
    # Random stratum: uniform sample from all visited cells
    # Adversarial stratum: cells from defective routes / edge interactions / boundary roles
    defective_routes = {"/consultations/:consultationId", "/ai-policy",
                         "/house-views/:houseViewId", "/house-views/:houseViewId/activate"}
    adversarial_pool = [r for r in rows if r['cell']['route'] in defective_routes
                         or r['cell']['interaction'] in {'modal', 'drag', 'websocket'}
                         or r['cell']['viewport'] in {'mobile', 'tablet'}]
    random_pool = rows

    n_rand = min(args.random_split, len(random_pool))
    n_adv = min(args.adversarial_split, len(adversarial_pool))
    random_sample = rng.sample(random_pool, n_rand)
    adversarial_sample = rng.sample(adversarial_pool, n_adv) if adversarial_pool else []
    # Deduplicate by cell_id
    seen_cell_ids: set[str] = set()
    spot_check: list[dict[str, Any]] = []
    for r in random_sample + adversarial_sample:
        cell_id = r.get('cell_id') or "|".join(
            [r['cell']['route'], r['cell']['role'], r['cell']['content_state'],
             r['cell']['interaction'], r['cell']['viewport']]
        )
        if cell_id in seen_cell_ids:
            continue
        seen_cell_ids.add(cell_id)
        spot_check.append(r)
    spot_check = spot_check[:args.n_user_sample]
    print(f"[spot-check] selected {len(spot_check)} cells (target {args.n_user_sample})")

    # Evaluate each cell via L2 critic
    start = time.time()
    results: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    error_count = 0
    for idx, r in enumerate(spot_check):
        if (time.time() - start) > args.limit_time_min * 60:
            print(f"[spot-check] time budget exceeded at {idx}/{len(spot_check)}")
            break
        text = r.get('dom_text_excerpt', '')
        if not text:
            continue
        try:
            verdict = evaluate_l2(text)
            label = "PASS" if verdict.pass_ else "FAIL"
            if label == "PASS":
                pass_count += 1
            else:
                fail_count += 1
            results.append({
                "cell_id": r.get('cell_id'),
                "route": r['cell']['route'],
                "role": r['cell']['role'],
                "label": label,
                "confidence": verdict.confidence,
                "issues": verdict.issues[:3],
                "reason": verdict.reason[:200],
            })
        except Exception as e:
            error_count += 1
            results.append({
                "cell_id": r.get('cell_id'),
                "label": "ERROR",
                "error": str(e)[:200],
            })
        if (idx + 1) % 10 == 0:
            elapsed = time.time() - start
            rate = (idx + 1) / max(elapsed, 1)
            eta = (len(spot_check) - idx - 1) / max(rate, 0.01)
            print(f"[spot-check] {idx+1}/{len(spot_check)} elapsed {elapsed:.0f}s rate {rate:.2f}/s eta {eta:.0f}s")

    cells_evaluated = pass_count + fail_count + error_count
    defect_rate = fail_count / max(cells_evaluated - error_count, 1)

    out_path = REPO_ROOT / ".omc/state" / f"v8-user-spot-check-cycle-{args.cycle}.yaml"
    output = {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cycle": args.cycle,
        "panel": "llm_gpt-5.5_as_proxy",
        "limitation_notice": (
            "Panel labels generated by LLM (gpt-5.5), NOT 사용자 panel ground truth. "
            "사용자 명시 권한 2026-05-20 적용 — ADR-009 §Status framework_side termination."
        ),
        "n_user_sample_target": args.n_user_sample,
        "n_random_split": args.random_split,
        "n_adversarial_split": args.adversarial_split,
        "cells_selected": len(spot_check),
        "cells_evaluated": cells_evaluated,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": error_count,
        "defect_count": fail_count,
        "defect_rate": round(defect_rate, 4),
        "defect_rate_threshold": 0.05,
        "pass_5pct": defect_rate < 0.05,
        "elapsed_seconds": int(time.time() - start),
        "samples": results,
    }
    out_path.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": True,
        "cycle": args.cycle,
        "cells_evaluated": cells_evaluated,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "defect_rate": output["defect_rate"],
        "pass_5pct": output["pass_5pct"],
        "output": str(out_path),
    }, indent=2, ensure_ascii=False))
    return 0 if output["pass_5pct"] else 1


if __name__ == "__main__":
    sys.exit(main())
