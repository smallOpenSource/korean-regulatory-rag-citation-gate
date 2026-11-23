#!/usr/bin/env python3
"""Phase C edge-case probe — invalid input + auth + role mismatch.

각 핵심 endpoint에 대해:
- 빈 body, missing required field → 422
- Invalid UUID, malformed JSON → 422
- Missing Authorization → 401
- Bogus token → 401
- Role mismatch (PB hits ADMIN endpoint) → 403
- 5xx 발생은 backend bug 후보.
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


def login(c: httpx.Client, email: str) -> str:
    r = c.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def record(results, label, resp, ok_codes):
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
    print(f"  [{tag}] {label:55s} → {resp.status_code} (expected {ok_codes})")


def main() -> int:
    results = []
    idem = {"Idempotency-Key": str(uuid.uuid4()), "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as c:
        pb_tk = login(c, PB)
        admin_tk = login(c, ADMIN)
        h_pb = {"Authorization": f"Bearer {pb_tk}", **idem}
        h_admin = {"Authorization": f"Bearer {admin_tk}", **idem}

        # ── Auth missing/bogus
        r = c.get(f"{BASE}/consultations")
        record(results, "1.missing_auth_get_consultations", r, (401,))

        r = c.get(
            f"{BASE}/consultations",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        record(results, "2.bogus_token", r, (401,))

        r = c.get(
            f"{BASE}/consultations", headers={"Authorization": "InvalidScheme abc"}
        )
        record(results, "3.malformed_auth_scheme", r, (401,))

        # ── Invalid UUID format
        r = c.patch(
            f"{BASE}/nba-actions/not-a-uuid/status",
            headers={**h_pb, "Idempotency-Key": str(uuid.uuid4())},
            json={"status_code": "DONE"},
        )
        record(results, "4.invalid_uuid_path_param", r, (422,))

        # ── Empty payload
        r = c.post(
            f"{BASE}/email-drafts",
            headers={**h_pb, "Idempotency-Key": str(uuid.uuid4())},
            json={},
        )
        record(results, "5.email_drafts_empty_body", r, (400, 422))

        # ── Missing required field (snoozed_until invalid format → 400)
        nba_random_uuid = str(uuid.uuid4())
        r = c.patch(
            f"{BASE}/nba-actions/{nba_random_uuid}/status",
            headers={**h_pb, "Idempotency-Key": str(uuid.uuid4())},
            json={"status_code": "SNOOZED", "snoozed_until": "not-a-date"},
        )
        record(results, "6.nba_snoozed_invalid_date", r, (400,))

        # ── Invalid status enum
        r = c.patch(
            f"{BASE}/nba-actions/{nba_random_uuid}/status",
            headers={**h_pb, "Idempotency-Key": str(uuid.uuid4())},
            json={"status_code": "GIBBERISH"},
        )
        record(results, "7.nba_invalid_status_enum", r, (400, 422))

        # ── Role mismatch (PB → ADMIN-only endpoint /house-views/{id}/review)
        random_hv = str(uuid.uuid4())
        r = c.post(
            f"{BASE}/house-views/{random_hv}/review",
            headers={**h_pb, "Idempotency-Key": str(uuid.uuid4())},
            json={},
        )
        record(results, "8.pb_hits_admin_hv_review", r, (403,))

        # ── Resource not found (valid UUID but doesn't exist)
        r = c.patch(
            f"{BASE}/disputes/{uuid.uuid4()}",
            headers={**h_pb, "Idempotency-Key": str(uuid.uuid4())},
            json={"resolution_status": "RESPONDED", "response_note": "test"},
        )
        record(results, "9.dispute_random_uuid", r, (404,))

        # ── Idempotency-Key absent (design 409)
        r = c.patch(
            f"{BASE}/nba-actions/{nba_random_uuid}/status",
            headers={"Authorization": f"Bearer {pb_tk}", "Content-Type": "application/json"},
            json={"status_code": "DONE"},
        )
        record(results, "10.missing_idempotency_key", r, (409, 422))

        # ── Idempotency-Key replay (same key same body → cached 200, different body → 409)
        idem_key = str(uuid.uuid4())
        hdrs = {**h_pb, "Idempotency-Key": idem_key}
        r1 = c.patch(
            f"{BASE}/nba-actions/{nba_random_uuid}/status",
            headers=hdrs,
            json={"status_code": "DONE"},
        )
        record(results, "11.idempotency_first_call_404", r1, (404,))
        r2 = c.patch(
            f"{BASE}/nba-actions/{nba_random_uuid}/status",
            headers=hdrs,
            json={"status_code": "DONE"},
        )
        record(results, "12.idempotency_replay_same_body", r2, (404, 200))

        # ── Same key, different body → 409
        r3 = c.patch(
            f"{BASE}/nba-actions/{nba_random_uuid}/status",
            headers=hdrs,
            json={"status_code": "DISMISSED"},
        )
        record(results, "13.idempotency_key_collision", r3, (409,))

    out_path = PROJECT_ROOT / "audit-out" / "bug-hunt" / "phase-c-edge.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False))

    fails = [r for r in results if not r["ok"]]
    ok = len(results) - len(fails)
    fives = [r for r in results if 500 <= r["status"] < 600]
    print(f"\n=== Phase C edge-case probe: {ok}/{len(results)} passed ===")
    print(f"=== 5xx detected: {len(fives)} ===")
    if fives:
        for r in fives:
            print(f"  [5xx] {r['step']} {r['status']} {r['snippet']}")
    return 0 if not fives else 2


if __name__ == "__main__":
    sys.exit(main())
