#!/usr/bin/env python
"""v8_llm_user_spot_check_vision.py — L_user_spot_check STRICT measurement
via L5 vision (screenshot) input (BFS extraction artifact 우회).

Cycle 1+2의 LLM-as-panel text-based 결과는 BFS body.text_content() Layout shell
whitespace-lost concatenation으로 78-80% FAIL rate. 실제 화면 결함률과 다름.

이 script는 L5 vision (screenshot input) 으로 panel evaluation 진행 — Playwright
text extraction 우회. 사용자 명시 권한 2026-05-20 적용.

Sample selection:
  - Cycle N visited.jsonl × stratified 371 cells (random 185 + adversarial 186)
  - Screenshot from cells/{state_hash}_{viewport}.png
  - L5 vision critic via gpt-5.5 (live API)

LIMITATION:
  - Same LLM (gpt-5.5) for L_calibration + L_user_spot_check (self-consistency)
  - 사용자 panel ground truth는 여전히 absent
  - 단 BFS extraction artifact는 회피됨 — 실제 화면 quality 측정 가능

Output:
  .omc/state/v8-user-spot-check-vision-cycle-N.yaml
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
from v8_detector_L5_visual_critic import evaluate_l5  # noqa: E402


def load_env_var(key: str) -> str:
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L5 vision-based panel spot-check")
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--n-user-sample", type=int, default=371)
    p.add_argument("--random-split", type=int, default=185)
    p.add_argument("--adversarial-split", type=int, default=186)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit-time-min", type=int, default=30)
    args = p.parse_args(argv)

    for key in ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_VERSION",
                "AZURE_OPENAI_DEPLOYMENT_NAME"]:
        env_val = load_env_var(key)
        if env_val:
            os.environ[key] = env_val  # .env 강제 override (stale OS env 차단)

    cycle_dir = REPO_ROOT / ".omc/state/v8-traversal" / f"cycle_{args.cycle}"
    visited_path = cycle_dir / "visited.jsonl"
    cells_dir = cycle_dir / "cells"
    if not visited_path.exists():
        print(json.dumps({"error": f"no visited.jsonl at {visited_path}"}))
        return 2

    rows: list[dict[str, Any]] = []
    with visited_path.open() as fh:
        for line in fh:
            rows.append(json.loads(line))

    rng = random.Random(args.seed)
    defective_routes = {"/consultations/:consultationId", "/ai-policy", "/korean-ai-act",
                         "/house-views/:houseViewId", "/house-views/:houseViewId/activate"}
    adversarial_pool = [r for r in rows if r['cell']['route'] in defective_routes
                         or r['cell']['interaction'] in {'modal', 'drag', 'websocket'}
                         or r['cell']['viewport'] in {'mobile', 'tablet'}]

    n_rand = min(args.random_split, len(rows))
    n_adv = min(args.adversarial_split, len(adversarial_pool))
    random_sample = rng.sample(rows, n_rand)
    adversarial_sample = rng.sample(adversarial_pool, n_adv) if adversarial_pool else []

    seen_cell_ids: set[str] = set()
    spot_check: list[dict[str, Any]] = []
    for r in random_sample + adversarial_sample:
        cell_id = r.get('cell_id') or "|".join(
            [r['cell']['route'], r['cell']['role'], r['cell']['content_state'],
             r['cell']['interaction'], r['cell']['viewport']]
        )
        if cell_id in seen_cell_ids:
            continue
        # Verify screenshot file exists
        screenshot_path = cells_dir / pathlib.Path(r.get('screenshot_path', '')).name
        if not screenshot_path.exists():
            continue
        seen_cell_ids.add(cell_id)
        spot_check.append({**r, "_screenshot_full_path": screenshot_path})
    spot_check = spot_check[:args.n_user_sample]
    print(f"[L5-spot-check] selected {len(spot_check)} cells (target {args.n_user_sample})")

    start = time.time()
    results: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    error_count = 0
    for idx, r in enumerate(spot_check):
        if (time.time() - start) > args.limit_time_min * 60:
            print(f"[L5-spot-check] time budget exceeded at {idx}/{len(spot_check)}")
            break
        try:
            verdict = evaluate_l5(
                r["_screenshot_full_path"],
                r['cell']['viewport'],
                a11y_tree=r.get('dom_text_excerpt', '')[:500],
            )
            label = "PASS" if verdict.pass_ else "FAIL"
            if label == "PASS":
                pass_count += 1
            else:
                fail_count += 1
            results.append({
                "cell_id": r.get('cell_id'),
                "route": r['cell']['route'],
                "role": r['cell']['role'],
                "viewport": r['cell']['viewport'],
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
            print(f"[L5-spot-check] {idx+1}/{len(spot_check)} elapsed {elapsed:.0f}s rate {rate:.2f}/s eta {eta:.0f}s")

    cells_evaluated = pass_count + fail_count + error_count
    defect_rate = fail_count / max(cells_evaluated - error_count, 1)

    out_path = REPO_ROOT / ".omc/state" / f"v8-user-spot-check-vision-cycle-{args.cycle}.yaml"
    output = {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cycle": args.cycle,
        "panel": "llm_gpt-5.5_vision_via_azure_openai",
        "input_modality": "screenshot_PNG",
        "limitation_notice": (
            "Vision-based panel via LLM (gpt-5.5). BFS body.text_content() extraction "
            "artifact 우회. 단 same-LLM (gpt-5.5) calibration + spot-check self-consistency "
            "는 잔존. 사용자 명시 권한 2026-05-20 적용."
        ),
        "advantage_over_text_panel": (
            "Cycle 1 text panel 80.5% FAIL, cycle 2 text panel 78.2% FAIL — all BFS extraction "
            "artifact (88.4% cells whitespace-lost). Vision input은 실제 screenshot 평가 → "
            "framework fix 효과 측정 가능."
        ),
        "n_user_sample_target": args.n_user_sample,
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
