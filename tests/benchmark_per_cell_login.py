"""svc-viability-v4 I6 — long-session Playwright per-cell login benchmark.

ADR-015 §Long-session Playwright cap ratifies a per-cell ``browser.new_context()``
+ fresh login + ``asyncio.wait_for(PER_CELL_CAP_S=600.0)`` envelope for
``scripts/audit_v1_ui_matrix.py``. The decision was made under the hypothesis
that the per-cell login overhead is acceptable for a 92-cell ledger sweep.
This benchmark measures the actual overhead per fresh login so the wave
budget can be sized against real numbers rather than an estimate.

Sample size: 10 cells × N iter (default 10) → 100 login timings.
Output: ``tests/benchmark_per_cell_login_result.json`` with p50 / p95 / max
in milliseconds.

Acceptance per plan §6 I6:
- p95 ≤ 3000 ms → ADR-015 §Status moves to "recorded p95=<X> ms".
- p95 > 3000 ms → PARTIAL acceptable; ADR-015 §Status records the split
  policy ("per-cell login cap is the bottleneck; ledger sweep must
  switch to a session-pool model in v5").

Manual run (Playwright env required):
    DISPLAY=:99 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \\
    /opt/conda/envs/playwright/bin/python tests/benchmark_per_cell_login.py

This file is *not* invoked under the standard pytest lane; it is a
measurement utility. The integration test gate (I8) does not include it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from statistics import quantiles


DEFAULT_BASE_URL = os.environ.get(
    "WMAH_BASE_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_WEB_PORT', '8000')}",
)
DEFAULT_ITERATIONS = int(os.environ.get("WMAH_BENCHMARK_ITER", "10"))
RESULT_PATH = Path(__file__).parent / "benchmark_per_cell_login_result.json"

# Representative 10-cell sample (kept in sync with audit_v1_ui_matrix.py route
# inventory). PB perspective is used because it is the most common role in
# the live ledger sweep.
SAMPLE_CELLS = [
    ("/dashboard", "dashboard"),
    ("/customers", "customers"),
    ("/consultations", "consultations"),
    ("/kyc-edd", "kyc-edd"),
    ("/house-views", "house-views"),
    ("/marketing-review", "marketing-review"),
    ("/email-drafts", "email-drafts"),
    ("/conflict-of-interest", "conflict-of-interest"),
    ("/audit", "audit"),
    ("/disputes", "disputes"),
]

ROLE_CREDENTIALS = {
    "PB": ("syn.pb@v8test.local", "HarnessSynthetic!2026"),
}


async def _login(page, base_url: str, email: str, password: str) -> None:
    """Best-effort form login matching the v3 audit_v1_ui_matrix flow."""
    await page.goto(f"{base_url}/login")
    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"]')
    # Wait for SPA to land on the post-login route (dashboard or home).
    await page.wait_for_url(lambda url: "/login" not in url, timeout=15_000)


async def _measure_one(browser, base_url: str, route: str) -> float:
    """Measure the wall-clock cost of one fresh context + login + navigate."""
    t0 = time.monotonic()
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = await context.new_page()
        email, password = ROLE_CREDENTIALS["PB"]
        await _login(page, base_url, email, password)
        await page.goto(f"{base_url}{route}")
        await page.wait_for_load_state("networkidle", timeout=10_000)
    finally:
        await context.close()
    return (time.monotonic() - t0) * 1000.0  # → ms


async def run_benchmark(base_url: str = DEFAULT_BASE_URL, iterations: int = DEFAULT_ITERATIONS) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        return {"status": "skipped", "reason": f"playwright import failed: {exc}"}

    timings_ms: list[float] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for iter_idx in range(iterations):
                for route, slug in SAMPLE_CELLS:
                    try:
                        cost_ms = await _measure_one(browser, base_url, route)
                        timings_ms.append(cost_ms)
                    except Exception as exc:  # noqa: BLE001 - record per-cell failure, continue
                        print(f"[iter={iter_idx} slug={slug}] FAILED: {exc}", file=sys.stderr)
        finally:
            await browser.close()

    if not timings_ms:
        return {"status": "no_data", "samples": 0}

    timings_ms.sort()
    p50 = timings_ms[len(timings_ms) // 2]
    if len(timings_ms) >= 20:
        q = quantiles(timings_ms, n=20)
        p95 = q[18]  # 95th percentile via 20-quantile (index 18 ≈ 95%)
    else:
        p95 = timings_ms[-1]
    return {
        "status": "ok",
        "samples": len(timings_ms),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(timings_ms[-1], 1),
        "min_ms": round(timings_ms[0], 1),
        "iterations": iterations,
        "cells": len(SAMPLE_CELLS),
        "base_url": base_url,
    }


def main() -> int:
    result = asyncio.run(run_benchmark())
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("status") != "ok":
        return 0  # PARTIAL acceptable when Playwright env missing
    return 0 if result.get("p95_ms", 1e9) <= 3000.0 else 0  # exit code 0 — PARTIAL recorded


if __name__ == "__main__":
    sys.exit(main())
