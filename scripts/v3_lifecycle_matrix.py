#!/usr/bin/env python3
"""Phase B lifecycle matrix — 11 entity × all status transitions.

각 entity 1+ row를 dynamic pick → 가능한 lifecycle transition을 모두 호출.
응답 status + audit_log row delta 측정. 5xx 발생은 backend bug 후보.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import asyncio
import httpx
from dotenv import load_dotenv


def idem() -> dict:
    """Per-call unique Idempotency-Key + JSON header."""
    return {"Idempotency-Key": str(uuid.uuid4())}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

BASE = f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}"
PASSWORD = "HarnessSynthetic!2026"
PB = "synthetic.pb1@example.invalid"
ADMIN = "synthetic.admin@example.invalid"
WM = "synthetic.wm1@example.invalid"

DSN = os.environ["DATABASE_URL"]


async def pick_resources() -> dict:
    """Dynamic row selection per entity (PB1-scoped where PB/WM is required)."""
    conn = await asyncpg.connect(DSN)
    pb1_id = "22222222-2222-2222-2222-222222222201"
    try:
        nba = await conn.fetch(
            "SELECT n.id::text, n.customer_id::text FROM nba_actions n "
            "JOIN customers c ON c.id = n.customer_id "
            "WHERE n.status_code='PENDING' AND c.assigned_pb_id=$1::uuid LIMIT 3",
            pb1_id,
        )
        after = await conn.fetch(
            "SELECT a.id::text FROM aftercare_events a "
            "JOIN customers c ON c.id=a.customer_id "
            "WHERE a.status_code='OPEN' AND c.assigned_pb_id=$1::uuid LIMIT 2",
            pb1_id,
        )
        email = await conn.fetch(
            "SELECT id::text FROM email_drafts WHERE status_code='DRAFT' AND employee_id=$1::uuid LIMIT 1",
            pb1_id,
        )
        hv = await conn.fetch(
            "SELECT id::text FROM house_views WHERE status_code='GENERATED' LIMIT 2"
        )
        consent = await conn.fetch(
            "SELECT id::text, customer_id::text, consent_type FROM customer_consents "
            "WHERE withdrawn_at IS NULL AND consent_type<>'MARKETING_CONTACT' LIMIT 1"
        )
        info = await conn.fetch(
            "SELECT id::text FROM info_access_requests WHERE responded_at IS NULL LIMIT 1"
        )
        dispute = await conn.fetch(
            "SELECT id::text FROM dispute_cases WHERE status='OPEN' LIMIT 1"
        )
        kyc = await conn.fetch(
            "SELECT id::text FROM kyc_edd_triggers WHERE status='OPEN' LIMIT 1"
        )
        return {
            "nba": [(r["id"], r["customer_id"]) for r in nba],
            "after": [r["id"] for r in after],
            "email_draft": email[0]["id"] if email else None,
            "hv_generated": [r["id"] for r in hv],
            "consent": (consent[0]["id"], consent[0]["customer_id"], consent[0]["consent_type"])
            if consent else None,
            "info": info[0]["id"] if info else None,
            "dispute": dispute[0]["id"] if dispute else None,
            "kyc": kyc[0]["id"] if kyc else None,
        }
    finally:
        await conn.close()


async def audit_count() -> int:
    conn = await asyncpg.connect(DSN)
    try:
        return await conn.fetchval("SELECT count(*) FROM audit_logs")
    finally:
        await conn.close()


def login(client: httpx.Client, email: str) -> str:
    r = client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def record(results: list, label: str, resp: httpx.Response, ok_codes=(200, 201, 202)):
    ok = resp.status_code in ok_codes
    results.append(
        {
            "step": label,
            "status": resp.status_code,
            "ok": ok,
            "snippet": resp.text[:200].replace("\n", " "),
        }
    )
    tag = "ok" if ok else "FAIL"
    print(f"  [{tag}] {label:40s} → {resp.status_code}")


async def main() -> int:
    resources = await pick_resources()
    print("=== Picked resources ===")
    for k, v in resources.items():
        print(f"  {k}: {v}")

    before_audit = await audit_count()
    results: list = []

    with httpx.Client(timeout=60.0) as c:
        pb = login(c, PB)
        admin = login(c, ADMIN)
        wm_tk = login(c, WM)
        h_pb = {"Authorization": f"Bearer {pb}", "Content-Type": "application/json"}
        h_admin = {"Authorization": f"Bearer {admin}", "Content-Type": "application/json"}
        h_wm = {"Authorization": f"Bearer {wm_tk}", "Content-Type": "application/json"}

        # 1. NBA — PATCH PENDING → DONE / SNOOZED (timestamptz) / DISMISSED
        if len(resources["nba"]) >= 3:
            nba_done, nba_snooze, nba_dismiss = resources["nba"]
            r = c.patch(
                f"{BASE}/nba-actions/{nba_done[0]}/status",
                headers={**h_pb, **idem()},
                json={"status_code": "DONE"},
            )
            record(results, "1.nba_done(PB)", r)

            r = c.patch(
                f"{BASE}/nba-actions/{nba_snooze[0]}/status",
                headers={**h_pb, **idem()},
                json={
                    "status_code": "SNOOZED",
                    "snoozed_until": "2026-06-30T00:00:00Z",
                },
            )
            record(results, "2.nba_snoozed", r)

            r = c.patch(
                f"{BASE}/nba-actions/{nba_dismiss[0]}/status",
                headers={**h_pb, **idem()},
                json={"status_code": "DISMISSED"},
            )
            record(results, "3.nba_dismissed", r)
        else:
            print("  [SKIP] NBA — insufficient PENDING rows")

        # 2. Aftercare — POST /resolve + /complete (PB scope)
        if len(resources["after"]) >= 1:
            r = c.post(
                f"{BASE}/aftercare-events/{resources['after'][0]}/resolve",
                headers={**h_pb, **idem()},
                json={"notes": "synthetic resolve (lifecycle)"},
            )
            record(results, "4.aftercare_resolve", r)
        if len(resources["after"]) >= 2:
            r = c.post(
                f"{BASE}/aftercare-events/{resources['after'][1]}/complete",
                headers={**h_pb, **idem()},
                json={"notes": "synthetic complete (lifecycle)"},
            )
            record(results, "5.aftercare_complete", r)

        # 3. Email drafts — DRAFT → /submit (PB) → /approve (ADMIN) → /send (ADMIN)
        if resources["email_draft"]:
            eid = resources["email_draft"]
            r = c.post(
                f"{BASE}/email-drafts/{eid}/submit",
                headers={**h_pb, **idem()},
                json={},
            )
            record(results, "6.email_submit", r)
            # 4-eye: approver must be PB/WM and ≠ author. PB1 wrote → use WM.
            r = c.post(
                f"{BASE}/email-drafts/{eid}/approve",
                headers={**h_wm, **idem()},
                json={"approver_note": "synthetic approve"},
            )
            record(results, "7.email_approve", r)
            r = c.post(
                f"{BASE}/email-drafts/{eid}/send",
                headers={**h_wm, **idem()},
                json={},
            )
            record(results, "8.email_send", r)

        # 4. House view — GENERATED → /review → /activate-lifecycle (2-step lifecycle)
        hv_list = resources["hv_generated"]
        if len(hv_list) >= 1:
            hv = hv_list[0]
            r = c.post(
                f"{BASE}/house-views/{hv}/review", headers={**h_admin, **idem()}, json={}
            )
            record(results, "9a.hv_review", r)
            r = c.post(
                f"{BASE}/house-views/{hv}/activate-lifecycle",
                headers={**h_admin, **idem()},
                json={},
            )
            record(results, "9b.hv_activate_lifecycle", r)

        # 5. Consent withdraw
        if resources["consent"]:
            cid, custid, ctype = resources["consent"]
            r = c.post(
                f"{BASE}/consents/withdraw",
                headers={**h_pb, **idem()},
                json={"customer_id": custid, "consent_type": ctype},
            )
            record(results, "11.consent_withdraw", r)

        # 6. Info access — respond
        if resources["info"]:
            r = c.post(
                f"{BASE}/info-access-requests/{resources['info']}/respond",
                headers={**h_pb, **idem()},
                json={"response_summary_redacted": "[SYN] lifecycle response"},
            )
            record(results, "12.info_respond", r)

        # 7. Dispute additional cycle (verify SQL fix idempotent)
        if resources["dispute"]:
            d = resources["dispute"]
            r = c.patch(
                f"{BASE}/disputes/{d}",
                headers={**h_pb, **idem()},
                json={"resolution_status": "RESPONDED", "response_note": "[SYN] lifecycle"},
            )
            record(results, "13.dispute_respond", r)
            # Resolve with a DISTINCT actor (WM) — the responder above was PB; the
            # dispute same_actor 4-eye block 403s a same-actor resolve (a control
            # success, not a lifecycle failure). WM is in _DISPUTE_WRITE_ROLES.
            r = c.patch(
                f"{BASE}/disputes/{d}",
                headers={**h_wm, **idem()},
                json={"resolution_status": "RESOLVED", "resolution_note": "[SYN] lifecycle"},
            )
            record(results, "14.dispute_resolve", r)

        # 8. KYC EDD additional cycle
        if resources["kyc"]:
            k = resources["kyc"]
            r = c.post(
                f"{BASE}/kyc-edd/triggers/{k}/reassess",
                headers={**h_admin, **idem()},
                json={"reason_text": "[SYN] lifecycle reassess"},
            )
            record(results, "15.kyc_reassess", r)
            r = c.post(
                f"{BASE}/kyc-edd/triggers/{k}/complete",
                headers={**h_admin, **idem()},
                json={"resolution": "[SYN] lifecycle complete"},
            )
            record(results, "16.kyc_complete", r)

    after_audit = await audit_count()
    print(f"\n=== Audit log delta: {after_audit - before_audit} new rows ===")

    out_path = PROJECT_ROOT / "audit-out" / "bug-hunt" / "phase-b-lifecycle.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "audit_delta": after_audit - before_audit,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    fails = [r for r in results if not r["ok"]]
    ok = len(results) - len(fails)
    print(f"\n=== Phase B lifecycle matrix: {ok}/{len(results)} passed ===")
    if fails:
        print("\nFailures detail:")
        for r in fails:
            print(f"  [{r['status']}] {r['step']}")
            print(f"      {r['snippet']}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
