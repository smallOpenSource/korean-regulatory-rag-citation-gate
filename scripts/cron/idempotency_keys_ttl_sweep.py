#!/usr/bin/env python
"""24h TTL sweep for the idempotency_keys table (ADR-011 §Server Pipeline).

Designed to run out-of-band — never in the request handler — so a busy
endpoint never inherits cleanup latency. The default cadence is hourly;
the TTL is 24 hours. Both values are env-overridable to support cron
slots that prefer different windows.

Usage:
    python scripts/cron/idempotency_keys_ttl_sweep.py
    IDEMPOTENCY_TTL_HOURS=12 python scripts/cron/idempotency_keys_ttl_sweep.py

Exit codes:
    0 — sweep ran (the row count is logged regardless of how many rows
        were actually deleted; an empty sweep still exits 0).
    1 — DSN missing or unreachable; the run is aborted before any DELETE.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)

LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "cron"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "idempotency_keys_ttl_sweep.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("idempotency_ttl_sweep")


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log.error("DATABASE_URL is not set; aborting sweep")
        return 1

    # IDEMPOTENCY_TTL_HOURS 파싱 실패(비정수)는 잡지 못한 ValueError로 이어지므로
    # 명시적으로 처리합니다. 0 이하 값도 의미 없는 sweep이라 거부합니다.
    raw = os.environ.get("IDEMPOTENCY_TTL_HOURS", "24")
    try:
        ttl_hours = int(raw)
    except ValueError:
        log.error("IDEMPOTENCY_TTL_HOURS is not an integer; aborting sweep")
        return 1
    if ttl_hours <= 0:
        log.error("IDEMPOTENCY_TTL_HOURS must be a positive integer; aborting sweep")
        return 1
    sql = "DELETE FROM idempotency_keys WHERE created_at < now() - make_interval(hours => %s)"

    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, (ttl_hours,))
            deleted = cur.rowcount
            conn.commit()
    except psycopg.OperationalError as exc:
        log.error("Patroni unreachable: %s", exc)
        return 1
    except psycopg.Error as exc:
        log.error("idempotency sweep DB error: %s", exc)
        return 1

    log.info("idempotency_keys sweep complete: deleted=%d ttl_hours=%d", deleted, ttl_hours)
    return 0


if __name__ == "__main__":
    sys.exit(main())
