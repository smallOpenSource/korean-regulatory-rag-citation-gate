#!/usr/bin/env python
"""v8_resolve_fixture_ids.py — Stage 2 cycle 1 launch precondition

DB에서 v8 BFS visitor의 :param URL 치환에 사용할 real synthetic IDs를 추출하여
.omc/state/v8-fixture-ids.json 박제.

Required for /customers/:customerId, /consultations/:consultationId,
/house-views/:houseViewId routes to return protected content (not /login redirect).

batch_jobs table은 V*.sql migrations에 부재 — /batch route는 그대로 navigate
(ai_jobs runtime page 표시) 또는 unreachable_manifest 박제.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys

import asyncpg  # type: ignore[import-not-found]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
OUT = REPO_ROOT / ".omc/state/v8-fixture-ids.json"


def load_env_var(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    if not m:
        return ""
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
        val = val[1:-1]
    return val


async def main() -> int:
    dsn = load_env_var("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL missing")
        return 2

    conn = await asyncpg.connect(dsn=dsn, timeout=10.0)
    try:
        # customer_no (used for /customers/:customerId)
        customer_no = await conn.fetchval(
            "SELECT customer_no FROM customers WHERE is_active = TRUE "
            "ORDER BY created_at ASC LIMIT 1"
        )
        # consultation id
        consultation_id = await conn.fetchval(
            "SELECT id::text FROM consultations ORDER BY consultation_at DESC LIMIT 1"
        )
        # house_view id
        house_view_id = await conn.fetchval(
            "SELECT id::text FROM house_views ORDER BY created_at DESC LIMIT 1"
        )
        # nba action id (for /nba detail navigation if needed)
        nba_id = await conn.fetchval(
            "SELECT id::text FROM nba_actions ORDER BY created_at DESC LIMIT 1"
        )
        # email draft id
        email_id = await conn.fetchval(
            "SELECT id::text FROM email_drafts ORDER BY created_at DESC LIMIT 1"
        )
        # aftercare event id
        aftercare_id = await conn.fetchval(
            "SELECT id::text FROM aftercare_events ORDER BY created_at DESC LIMIT 1"
        )
    finally:
        await conn.close()

    if customer_no is None:
        print(
            "WARN: no active customer found, using SYN-CUSTOMER-001 fallback",
            file=sys.stderr,
        )
    fixtures = {
        "customerId": customer_no or "SYN-CUSTOMER-001",
        "consultationId": consultation_id,
        "houseViewId": house_view_id,
        "nbaId": nba_id,
        "emailDraftId": email_id,
        "aftercareId": aftercare_id,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(fixtures, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "fixture_count": sum(1 for v in fixtures.values() if v),
        "fixtures": {k: (v if not (v and len(v) == 36) else v[:8] + "...") for k, v in fixtures.items()},
        "output": str(OUT),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
