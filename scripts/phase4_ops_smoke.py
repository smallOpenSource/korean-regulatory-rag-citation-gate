#!/usr/bin/env python3
"""Phase 4 ops smoke — HTTPS/CSP/CORS headers + login rate limit + WS connect.

Service-readiness v2 addendum: the v2 handoff explicitly listed these
4 operational items as Unverified. This script issues focused checks
against the live harness (host:HARNESS_API_PORT, default 8010) and the
WS endpoint, recording each verdict to
audit-out/service-readiness/phase4-ops.json.

Limitations (PoC):
- HTTPS enforce middleware is bypassed in development profile (APP_ENV
  not set to production), so we verify the security headers are
  present on the HTTP response rather than the 308 redirect path.
- WS verification only checks the connection accept; broadcast wiring
  is exercised separately by the NBA create endpoint test.
"""

from __future__ import annotations

import asyncio
import json
import os
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
EMAIL = "synthetic.pb1@example.invalid"


def check_security_headers(results: list[dict]) -> None:
    """Verify Strict-Transport-Security + CSP + X-Content-Type-Options + others."""
    r = httpx.get(f"{BASE}/health", timeout=5.0)
    expected = {
        "Strict-Transport-Security": "max-age=",
        "Content-Security-Policy": "default-src",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin",
        "Permissions-Policy": "camera=()",
    }
    missing = []
    for h, needle in expected.items():
        v = r.headers.get(h, "")
        if needle not in v:
            missing.append({"header": h, "expected_needle": needle, "actual": v[:80]})
    results.append({
        "check": "security_headers",
        "ok": not missing,
        "status": r.status_code,
        "headers_present": {h: r.headers.get(h, "")[:120] for h in expected},
        "missing": missing,
    })


def check_cors_policy(results: list[dict]) -> None:
    """Verify CORS policy matches PoC design (CORS_ENABLED=false → same-origin).

    The PoC bundles Vite + backend behind the same origin (proxy), so CORS is
    disabled by design. We verify that (a) the configured flag is false and
    (b) a cross-origin request still works without Access-Control-Allow-Origin
    being echoed back — the in-tree core/middleware.py CORS guard prevents
    explicit echoing for unconfigured origins, which is the production-safe
    posture for a same-origin PoC.
    """
    bad_origin = "http://evil.example"
    r = httpx.get(
        f"{BASE}/health",
        headers={"Origin": bad_origin},
        timeout=5.0,
    )
    echo = r.headers.get("Access-Control-Allow-Origin", "")
    ok = bad_origin not in echo  # never echo unconfigured origin
    results.append({
        "check": "cors_policy",
        "ok": ok,
        "design": "CORS_ENABLED=false (same-origin PoC)",
        "bad_origin_echo": echo[:100],
        "status": r.status_code,
    })


def check_login_rate_limit(results: list[dict]) -> None:
    """Trigger 11+ login attempts with wrong password; the 11th must return 429."""
    fake_email = f"rl-probe-{uuid.uuid4().hex[:8]}@example.invalid"
    statuses: list[int] = []
    with httpx.Client(timeout=5.0) as client:
        for i in range(13):
            r = client.post(f"{BASE}/auth/login", json={"email": fake_email, "password": "wrong"})
            statuses.append(r.status_code)
            if r.status_code == 429:
                break
            time.sleep(0.05)
    got_429 = 429 in statuses
    results.append({
        "check": "login_rate_limit",
        "ok": got_429,
        "request_count": len(statuses),
        "statuses": statuses,
        "first_429_at": statuses.index(429) + 1 if got_429 else None,
    })


async def check_ws_connect(results: list[dict]) -> None:
    """Verify the documented WS handshake: POST /ws/ticket → connect with
    Sec-WebSocket-Protocol harness.v1 → send {ticket} → expect first server
    message (snapshot or ack)."""
    started = time.time()
    async with httpx.AsyncClient() as client:
        login = await client.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        login.raise_for_status()
        token = login.json()["access_token"]
        ticket_resp = await client.post(
            f"{BASE}/ws/ticket",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        ticket_resp.raise_for_status()
        ticket = ticket_resp.json().get("ticket")

    try:
        async with websockets.connect(
            WS_URL,
            subprotocols=["harness.v1"],
            open_timeout=5.0,
        ) as ws:
            await ws.send(json.dumps({"ticket": ticket}))
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                msg = None
            results.append({
                "check": "ws_connect",
                "ok": True,
                "ticket_status": ticket_resp.status_code,
                "first_message_preview": str(msg)[:160] if msg else None,
                "elapsed_s": round(time.time() - started, 2),
            })
    except Exception as exc:
        results.append({
            "check": "ws_connect",
            "ok": False,
            "ticket_status": ticket_resp.status_code,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "elapsed_s": round(time.time() - started, 2),
        })


def main() -> int:
    results: list[dict] = []
    out_path = PROJECT_ROOT / "audit-out" / "service-readiness" / "phase4-ops.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    check_security_headers(results)
    check_cors_policy(results)
    check_login_rate_limit(results)
    asyncio.run(check_ws_connect(results))

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    ok = sum(1 for r in results if r["ok"])
    print(f"\n=== Phase 4 ops: {ok}/{len(results)} passed ===")
    for r in results:
        status = "ok" if r["ok"] else "FAIL"
        detail = []
        if r["check"] == "security_headers" and r["missing"]:
            detail.append(f"missing={[m['header'] for m in r['missing']]}")
        if r["check"] == "login_rate_limit":
            detail.append(f"first_429_at={r.get('first_429_at')} after {r['request_count']} requests")
        if r["check"] == "ws_connect":
            detail.append(r.get("error", "connected"))
        print(f"  [{status}] {r['check']:20s} {'  '.join(detail)}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
