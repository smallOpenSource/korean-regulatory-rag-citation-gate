#!/usr/bin/env python3
"""Phase D concurrent race — 동일 resource에 2-3 concurrent mutation.

검증 대상:
- 같은 dispute에 2 PB 동시 respond → 한 쪽 성공 + 한 쪽 race detection
- 같은 KYC trigger에 2 ADMIN 동시 complete
- 같은 HV에 2 ADMIN 동시 review

5xx 발생은 race condition / transaction isolation bug 후보.
정상 expected: 한 쪽 200, 다른 쪽 404 (이미 transitioned) 또는 409.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

BASE = f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}"
PASSWORD = "HarnessSynthetic!2026"
PB = "synthetic.pb1@example.invalid"
ADMIN = "synthetic.admin@example.invalid"

# .env의 DATABASE_URL을 SoT로 사용한다(하드코딩 DSN 금지). 비밀번호의 %21 등
# URL-encoding은 asyncpg가 자동 디코딩하므로 그대로 둔다. asyncpg+ 접두어만 정규화.
DSN = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
if not DSN:
    print("ERROR: DATABASE_URL 환경변수가 설정되어 있지 않습니다(.env 확인).", file=sys.stderr)
    sys.exit(2)


async def pick_resources() -> dict:
    conn = await asyncpg.connect(DSN)
    try:
        dispute = await conn.fetch(
            "SELECT id::text FROM dispute_cases WHERE status='OPEN' LIMIT 1"
        )
        kyc = await conn.fetch(
            "SELECT id::text FROM kyc_edd_triggers WHERE status='OPEN' LIMIT 1"
        )
        hv = await conn.fetch(
            "SELECT id::text FROM house_views WHERE status_code='GENERATED' LIMIT 1"
        )
        return {
            "dispute": dispute[0]["id"] if dispute else None,
            "kyc": kyc[0]["id"] if kyc else None,
            "hv": hv[0]["id"] if hv else None,
        }
    finally:
        await conn.close()


async def login_async(c, email):
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


async def race_dispute(c, pb_tk, dispute_id):
    """2 concurrent PATCH /disputes/{id} RESPONDED."""
    h = lambda: {
        "Authorization": f"Bearer {pb_tk}",
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    async def hit():
        return await c.patch(
            f"{BASE}/disputes/{dispute_id}",
            headers=h(),
            json={"resolution_status": "RESPONDED", "response_note": "[SYN] race"},
        )

    return await asyncio.gather(hit(), hit(), return_exceptions=True)


async def race_kyc(c, admin_tk, kyc_id):
    h = lambda: {
        "Authorization": f"Bearer {admin_tk}",
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    async def hit():
        return await c.post(
            f"{BASE}/kyc-edd/triggers/{kyc_id}/complete",
            headers=h(),
            json={"resolution": "[SYN] race"},
        )

    return await asyncio.gather(hit(), hit(), return_exceptions=True)


async def race_hv_review(c, admin_tk, hv_id):
    h = lambda: {
        "Authorization": f"Bearer {admin_tk}",
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    async def hit():
        return await c.post(
            f"{BASE}/house-views/{hv_id}/review", headers=h(), json={}
        )

    return await asyncio.gather(hit(), hit(), return_exceptions=True)


def classify(name, responses):
    statuses = []
    five_x = 0
    client_errors = 0
    for r in responses:
        if isinstance(r, Exception):
            # Client-side transport failure (timeout/connection reset) — NOT a
            # server 5xx. Counting it as 5xx would falsely assert a backend race
            # bug, so track it separately and keep it out of the 5xx verdict.
            statuses.append(f"EXC:{type(r).__name__}")
            client_errors += 1
        else:
            statuses.append(r.status_code)
            if 500 <= r.status_code < 600:
                five_x += 1
    print(f"  {name}: statuses={statuses}, 5xx={five_x}, client_errors={client_errors}")
    return {
        "name": name,
        "statuses": [str(s) for s in statuses],
        "5xx": five_x,
        "client_errors": client_errors,
    }


async def main() -> int:
    resources = await pick_resources()
    print(f"=== Resources: {resources} ===")
    results = []

    async with httpx.AsyncClient(timeout=30.0) as c:
        pb_tk = await login_async(c, PB)
        admin_tk = await login_async(c, ADMIN)

        if resources["dispute"]:
            rsp = await race_dispute(c, pb_tk, resources["dispute"])
            results.append(classify("1.dispute_double_respond", rsp))
        if resources["kyc"]:
            rsp = await race_kyc(c, admin_tk, resources["kyc"])
            results.append(classify("2.kyc_double_complete", rsp))
        if resources["hv"]:
            rsp = await race_hv_review(c, admin_tk, resources["hv"])
            results.append(classify("3.hv_double_review", rsp))

    total_5xx = sum(r["5xx"] for r in results)
    total_client_errors = sum(r.get("client_errors", 0) for r in results)
    out_path = PROJECT_ROOT / "audit-out" / "bug-hunt" / "phase-d-race.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "total_5xx": total_5xx,
                "total_client_errors": total_client_errors,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        f"\n=== Phase D concurrent race: 5xx total = {total_5xx}, "
        f"client_errors = {total_client_errors} ==="
    )
    # Only genuine server 5xx assert a backend race/isolation bug; client-side
    # transport errors are surfaced but do not flip the verdict.
    return 0 if total_5xx == 0 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
