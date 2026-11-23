#!/usr/bin/env python
"""audit_v1_ui_post_hp1.py — Service Viability Audit v1 / Axis 1 (post-mutation)

Re-captures PB1 × 4 routes after HP1 mutation, per plan §3.0 Step 3.
Routes: /dashboard, /consultations/{id}, /email-drafts, /audit.

The HP1 mutation produced new consultation + email_draft rows (Step 2 commit a30968b).
This script captures the post-mutation UI state and emits diff vs baseline (Step 1).

Output: audit-out/service-viability-v1/axis-1/post-hp1/PB1__{slug}.{png|dom.html|console.json|network.json}
        audit-out/service-viability-v1/axis-1/post-hp1/diff_vs_baseline.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import audit_v1_ui_matrix helpers
import audit_v1_ui_matrix as M  # type: ignore[import-not-found]

OUTPUT_BASE = REPO_ROOT / "audit-out" / "service-viability-v1" / "axis-1"

# PB1 post-hp1 routes — plan §3.0 Step 3 명시 4 routes.
# /consultations/{id} → most recent HP1 consultation (or fixture).
# Other 3 routes are static list pages.
POST_HP1_ROUTES: list[tuple[str, str, str]] = [
    ("/dashboard",                       "dashboard",     "dashboard"),
    ("/consultations/:consultationId",   "consultation",  "consultation"),
    ("/email-drafts",                    "emailDrafts",   "email-drafts"),
    ("/audit",                           "audit",         "audit"),
]


async def main_async(base_url: str, output_dir: pathlib.Path) -> int:
    snapshots_dir = output_dir / "post-hp1"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    except ImportError as e:
        print(f"FATAL: playwright missing: {e}", flush=True)
        return 2

    results: list[dict[str, Any]] = []
    t0 = time.time()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()
            await M.login(page, base_url, "PB1")
            for route_pattern, routeKey, slug in POST_HP1_ROUTES:
                print(f"[PB1 post-hp1] capturing {slug}", flush=True)
                try:
                    rec = await M.capture_one(page, base_url, "PB1", route_pattern,
                                                routeKey, slug, snapshots_dir)
                except Exception as e:
                    rec = {"role": "PB1", "slug": slug, "fatal": f"{type(e).__name__}: {e!s:.200}",
                            "pass": False, "fail_reasons": ["top_level_exc"]}
                results.append(rec)
        finally:
            await browser.close()

    elapsed = int(time.time() - t0)

    # Diff vs baseline summary.json
    baseline_summary_path = output_dir / "summary.json"
    diff: dict[str, Any] = {"compared_against": str(baseline_summary_path)}
    if baseline_summary_path.exists():
        baseline = json.loads(baseline_summary_path.read_text())
        baseline_pb1 = {r["slug"]: r for r in baseline.get("snapshot_results", [])
                        if r.get("role") == "PB1"}
        per_route_diff: dict[str, dict[str, Any]] = {}
        for r in results:
            slug = r.get("slug", "")
            b = baseline_pb1.get(slug, {})
            per_route_diff[slug] = {
                "baseline_pass": b.get("pass"),
                "post_pass": r.get("pass"),
                "baseline_console_error": b.get("console_error_count", 0),
                "post_console_error": r.get("console_error_count", 0),
                "baseline_http_5xx": b.get("http_5xx_count", 0),
                "post_http_5xx": r.get("http_5xx_count", 0),
                "baseline_placeholder_count": len((b.get("findings") or {}).get("placeholder", [])),
                "post_placeholder_count": len((r.get("findings") or {}).get("placeholder", [])),
                "baseline_fail_reasons": b.get("fail_reasons", []),
                "post_fail_reasons": r.get("fail_reasons", []),
            }
        diff["per_route_diff"] = per_route_diff
    else:
        diff["baseline_missing"] = True

    summary = {
        "cycle": "service-viability-v1",
        "axis": "axis-1",
        "phase": "post-hp1",
        "role": "PB1",
        "routes_captured": len(results),
        "pass_count": sum(1 for r in results if r.get("pass")),
        "fail_count": sum(1 for r in results if not r.get("pass")),
        "elapsed_seconds": elapsed,
        "results": results,
        "diff_vs_baseline": diff,
    }
    (snapshots_dir / "diff_vs_baseline.json").write_text(
        json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (snapshots_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"DONE total={len(results)} pass={summary['pass_count']} fail={summary['fail_count']} elapsed={elapsed}s", flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Axis 1 post-hp1 PB1 4-route re-capture")
    default_base_url = f"http://127.0.0.1:{os.environ.get('HARNESS_WEB_PORT', '8000')}"
    p.add_argument("--base-url", default=default_base_url)
    p.add_argument("--output-dir", default=str(OUTPUT_BASE))
    args = p.parse_args()
    return asyncio.run(main_async(args.base_url, pathlib.Path(args.output_dir)))


if __name__ == "__main__":
    sys.exit(main())
