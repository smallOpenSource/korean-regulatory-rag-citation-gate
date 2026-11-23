#!/usr/bin/env python3
"""Phase 5 load/concurrency smoke (service-readiness v2 addendum).

Drives 4 concurrency scenarios against the live harness and measures
success rate + latency distribution. The targets are tuned for PoC
hardware (uvicorn workers=1, single Patroni HA endpoint, single Redis
Sentinel topology); the goal is to confirm graceful behavior under
modest concurrency, not to capacity-plan.

Scenarios:
    A. 50 concurrent GET /health           (warm-up baseline)
    B. 5 concurrent login as distinct roles (rate-limit isolated per user)
    C. 30 concurrent GET /house-views?limit=20  (cached read path)
    D. 10 concurrent POST /consultations    (distinct idempotency_keys)
    E. 10 concurrent WS connects + first server message

Output: audit-out/service-readiness/phase5-load.json + console table.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

BASE = f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}"
WS_URL = f"ws://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}/ws"
PASSWORD = "HarnessSynthetic!2026"

ROLE_EMAILS = [
    "synthetic.pb1@example.invalid",
    "synthetic.wm1@example.invalid",
    "synthetic.branch.manager@example.invalid",
    "synthetic.admin@example.invalid",
    "synthetic.audit@example.invalid",
]


def percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50": 0, "p95": 0, "p99": 0, "max": 0, "min": 0}
    s = sorted(samples)
    def pct(p: float) -> float:
        idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
        return round(s[idx] * 1000, 1)  # ms
    return {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99),
            "min": pct(0.0), "max": pct(1.0)}


async def login(client: httpx.AsyncClient, email: str) -> str:
    r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD}, timeout=10.0)
    r.raise_for_status()
    return r.json()["access_token"]


async def scenario_a_health(results: list) -> None:
    """50 concurrent GET /health."""
    started = time.time()
    async with httpx.AsyncClient() as c:
        async def one() -> tuple[int, float]:
            t0 = time.time()
            try:
                r = await c.get(f"{BASE}/health", timeout=10.0)
                return r.status_code, time.time() - t0
            except Exception:
                return 0, time.time() - t0
        outs = await asyncio.gather(*(one() for _ in range(50)))
    ok = sum(1 for s, _ in outs if s == 200)
    lat = [d for _, d in outs]
    results.append({
        "scenario": "A_health_50",
        "ok": ok == 50,
        "success": ok,
        "total": 50,
        "latency_ms": percentiles(lat),
        "wall_s": round(time.time() - started, 2),
    })


async def scenario_b_login_distinct(results: list) -> None:
    """5 concurrent logins as distinct roles (independent rate-limit buckets)."""
    started = time.time()
    async with httpx.AsyncClient() as c:
        async def one(email: str) -> tuple[int, float]:
            t0 = time.time()
            try:
                r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD}, timeout=10.0)
                return r.status_code, time.time() - t0
            except Exception:
                return 0, time.time() - t0
        outs = await asyncio.gather(*(one(e) for e in ROLE_EMAILS))
    ok = sum(1 for s, _ in outs if s == 200)
    lat = [d for _, d in outs]
    results.append({
        "scenario": "B_login_distinct_5",
        "ok": ok == 5,
        "success": ok,
        "total": 5,
        "latency_ms": percentiles(lat),
        "wall_s": round(time.time() - started, 2),
    })


async def scenario_c_houseviews_30(results: list) -> None:
    """30 concurrent GET /house-views?limit=20 (cached read)."""
    started = time.time()
    async with httpx.AsyncClient() as c:
        token = await login(c, "synthetic.pb1@example.invalid")
        headers = {"Authorization": f"Bearer {token}"}
        async def one() -> tuple[int, float]:
            t0 = time.time()
            try:
                r = await c.get(f"{BASE}/house-views?limit=20", headers=headers, timeout=10.0)
                return r.status_code, time.time() - t0
            except Exception:
                return 0, time.time() - t0
        outs = await asyncio.gather(*(one() for _ in range(30)))
    ok = sum(1 for s, _ in outs if s == 200)
    lat = [d for _, d in outs]
    results.append({
        "scenario": "C_houseviews_30",
        "ok": ok == 30,
        "success": ok,
        "total": 30,
        "latency_ms": percentiles(lat),
        "wall_s": round(time.time() - started, 2),
    })


async def scenario_d_consultations_10(results: list) -> None:
    """10 concurrent POST /consultations (distinct idempotency keys)."""
    started = time.time()
    async with httpx.AsyncClient() as c:
        token = await login(c, "synthetic.pb1@example.invalid")
        async def one() -> tuple[int, float]:
            t0 = time.time()
            try:
                r = await c.post(
                    f"{BASE}/consultations",
                    headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
                    json={"customer_id": "33333333-3333-3333-3333-333333333301", "channel_code": "FACE_TO_FACE"},
                    timeout=10.0,
                )
                return r.status_code, time.time() - t0
            except Exception:
                return 0, time.time() - t0
        outs = await asyncio.gather(*(one() for _ in range(10)))
    ok = sum(1 for s, _ in outs if s in (200, 201))
    lat = [d for _, d in outs]
    results.append({
        "scenario": "D_consultations_10",
        "ok": ok == 10,
        "success": ok,
        "total": 10,
        "latency_ms": percentiles(lat),
        "wall_s": round(time.time() - started, 2),
    })


async def scenario_e_ws_10(results: list) -> None:
    """10 concurrent WS connect (each acquires its own ticket)."""
    started = time.time()
    async with httpx.AsyncClient() as c:
        token = await login(c, "synthetic.pb1@example.invalid")
        async def one() -> tuple[bool, float]:
            t0 = time.time()
            try:
                tk = await c.post(f"{BASE}/ws/ticket", headers={"Authorization": f"Bearer {token}"}, timeout=5.0)
                tk.raise_for_status()
                ticket = tk.json()["ticket"]
                async with websockets.connect(WS_URL, subprotocols=["harness.v1"], open_timeout=5.0) as ws:
                    await ws.send(json.dumps({"ticket": ticket}))
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    return bool(msg), time.time() - t0
            except Exception:
                return False, time.time() - t0
        outs = await asyncio.gather(*(one() for _ in range(10)))
    ok = sum(1 for s, _ in outs if s)
    lat = [d for _, d in outs]
    results.append({
        "scenario": "E_ws_10",
        "ok": ok == 10,
        "success": ok,
        "total": 10,
        "latency_ms": percentiles(lat),
        "wall_s": round(time.time() - started, 2),
    })


async def main() -> int:
    results: list = []
    out_path = PROJECT_ROOT / "audit-out" / "service-readiness" / "phase5-load.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    await scenario_a_health(results)
    await scenario_b_login_distinct(results)
    await scenario_c_houseviews_30(results)
    await scenario_d_consultations_10(results)
    await scenario_e_ws_10(results)

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    ok = sum(1 for r in results if r["ok"])
    print(f"\n=== Phase 5 load/concurrency: {ok}/{len(results)} scenarios passed ===")
    print(f"{'scenario':25s} {'ok':>3s} {'total':>5s} {'p50':>6s} {'p95':>6s} {'p99':>6s} {'max':>6s} {'wall_s':>7s}")
    for r in results:
        lm = r["latency_ms"]
        status = "ok" if r["ok"] else "FAIL"
        print(f"{r['scenario']:25s} {r['success']:>3d}/{r['total']:<3d} {'':>1s} {lm['p50']:>5.1f} {lm['p95']:>6.1f} {lm['p99']:>6.1f} {lm['max']:>6.1f} {r['wall_s']:>6.2f}s  [{status}]")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
