#!/usr/bin/env python3
"""Step 3 — Dispute + KYC EDD lifecycle spot-check (service-readiness v2).

Phase 3 verified only the create endpoints; this step exercises the
full lifecycle transitions: dispute OPEN → RESPONDED → RESOLVED, and
KYC EDD OPEN → IN_PROGRESS (reassess) → CLOSED (complete).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

BASE = f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}"
PASSWORD = "HarnessSynthetic!2026"
PB = "synthetic.pb1@example.invalid"
ADMIN = "synthetic.admin@example.invalid"
CUST = "33333333-3333-3333-3333-333333333301"


def login(client: httpx.Client, email: str) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    results: list[dict] = []
    # V067 seed rows: dispute 88...1201 OPEN, KYC trigger 88...0601 OPEN
    SEEDED_DISPUTE = "88888888-8888-8888-8888-880000001201"
    SEEDED_KYC = "88888888-8888-8888-8888-880000000601"
    with httpx.Client(timeout=30.0) as c:
        pb_tk = login(c, PB)
        admin_tk = login(c, ADMIN)

        # 1. Respond to seeded OPEN dispute
        rp = c.patch(
            f"{BASE}/disputes/{SEEDED_DISPUTE}",
            headers={"Authorization": f"Bearer {pb_tk}", "Content-Type": "application/json"},
            json={"resolution_status": "RESPONDED", "response_note": "synthetic response (step3)"},
        )
        results.append({"step": "1.dispute_respond", "status": rp.status_code,
                       "ok": rp.status_code == 200,
                       "snippet": rp.text[:160]})

        # 2. Resolve — distinct actor required (4-eye): the responder above was PB,
        # so resolve with ADMIN (in _DISPUTE_WRITE_ROLES). A same-actor resolve is
        # 403'd by the disputes same_actor block, which is a control SUCCESS — not a
        # lifecycle failure to be recorded as ok=False.
        rs = c.patch(
            f"{BASE}/disputes/{SEEDED_DISPUTE}",
            headers={"Authorization": f"Bearer {admin_tk}", "Content-Type": "application/json"},
            json={
                "resolution_status": "RESOLVED",
                "resolution_note": "synthetic resolution (step3)",
            },
        )
        results.append({"step": "2.dispute_resolve", "status": rs.status_code,
                       "ok": rs.status_code == 200,
                       "snippet": rs.text[:160]})

        # 3. KYC EDD reassess seeded trigger
        kr = c.post(
            f"{BASE}/kyc-edd/triggers/{SEEDED_KYC}/reassess",
            headers={"Authorization": f"Bearer {admin_tk}", "Content-Type": "application/json"},
            json={"reason_text": "[SYN] step3 reassessment"},
        )
        results.append({"step": "3.kyc_reassess", "status": kr.status_code,
                       "ok": kr.status_code in (200, 201),
                       "snippet": kr.text[:160]})

        # 4. KYC EDD complete
        kc = c.post(
            f"{BASE}/kyc-edd/triggers/{SEEDED_KYC}/complete",
            headers={"Authorization": f"Bearer {admin_tk}", "Content-Type": "application/json"},
            json={"resolution": "verified (step3)"},
        )
        results.append({"step": "4.kyc_complete", "status": kc.status_code,
                       "ok": kc.status_code in (200, 201),
                       "snippet": kc.text[:160]})

    out_path = PROJECT_ROOT / "audit-out" / "service-readiness" / "step3-lifecycle.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    ok = sum(1 for r in results if r["ok"])
    print(f"\n=== Step 3 lifecycle spot-check: {ok}/{len(results)} passed ===")
    for r in results:
        tag = "ok" if r["ok"] else "FAIL"
        print(f"  [{tag}] {r['step']:25s} → {r['status']}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
