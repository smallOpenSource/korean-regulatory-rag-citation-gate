"""HouseView AI content backfill (W3-1, 2026-05-24).

Reads every house_views row whose ``asset_views_json::text = '{}'`` (i.e. the
fixture/seed populated the row with empty content), calls the in-process
``generate_house_view_content`` service (same code path as the live HTTP
endpoint, including ADR-005 sanitize + redact), and writes the result via
``advance_to_generated``.

The script connects directly to PostgreSQL via the project ``.env`` (override
mode so the canonical ``<active-azure-resource>`` Azure endpoint is honored).
It does NOT route through the HTTP API: no auth token is needed and the
Python service code is reused verbatim.

Concurrency is fixed at 2 because gpt-5.5 deployments quota at ~30 RPM
in this tenant; raising it would risk Azure rate-limit 429s. A 1-second
sleep is added between dispatches as an additional brake.

Idempotency: the WHERE clause (``asset_views_json::text = '{}'`` AND
``status_code = 'DRAFT'``) means rerunning the script after a partial
success picks up only the rows that still need work. No row is touched
twice unless explicitly forced via ``--include-non-empty``.

Usage:
    python scripts/backfill_house_view_content.py --dry-run
    python scripts/backfill_house_view_content.py --limit 5
    python scripts/backfill_house_view_content.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.repositories.house_views import advance_to_generated  # noqa: E402
from apps.api.harness.services.house_view import generate_house_view_content  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill_house_view")


SELECT_TARGETS_SQL = """
SELECT id, version_no, title, period_code, market, asset_class, region
FROM house_views
WHERE status_code = 'DRAFT' AND asset_views_json::text = '{}'
ORDER BY version_no ASC
"""


async def _process_one(
    pool: asyncpg.Pool,
    row: dict[str, Any],
    *,
    dry_run: bool,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool, str]:
    """Generate one HV. Returns (hv_id, ok, message)."""
    hv_id = str(row["id"])
    label = f"v{row['version_no']} {row['period_code']} ({hv_id[:8]})"
    if dry_run:
        return hv_id, True, f"[dry-run] would generate {label}"

    async with semaphore:
        try:
            result = await generate_house_view_content(
                market=row.get("market"),
                asset_class=row.get("asset_class"),
                region=row.get("region"),
                market_data_summary="",  # PoC seed has no per-row market data
                previous_house_view_summary="",
            )
            async with pool.acquire() as connection:
                await advance_to_generated(
                    connection,
                    house_view_id=hv_id,
                    generated_at=result.generated_at,
                    model_name=result.model,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    inputs_hash=result.inputs_hash,
                    content=result.content,
                    fail_closed_reason_code=result.fail_closed_reason_code,
                )
            await asyncio.sleep(1.0)  # rate-limit brake
            tag = "FAIL_CLOSED" if result.fail_closed_reason_code else "ok"
            return hv_id, True, (
                f"{label} → {tag} "
                f"(prompt={result.prompt_tokens}, completion={result.completion_tokens})"
            )
        except Exception as exc:  # noqa: BLE001
            return hv_id, False, f"{label} → ERROR {type(exc).__name__}: {str(exc)[:200]}"


async def main(*, dry_run: bool, limit: int | None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        logger.error("DATABASE_URL not set after loading .env")
        return 2
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=4)
    try:
        rows = [dict(r) for r in await pool.fetch(SELECT_TARGETS_SQL)]
        if limit is not None:
            rows = rows[:limit]
        logger.info("targets: %d house_views (dry_run=%s)", len(rows), dry_run)
        if not rows:
            logger.info("nothing to do.")
            return 0

        started = datetime.now()
        semaphore = asyncio.Semaphore(2)
        tasks = [
            _process_one(pool, row, dry_run=dry_run, semaphore=semaphore)
            for row in rows
        ]
        done = 0
        ok = 0
        for coro in asyncio.as_completed(tasks):
            hv_id, success, msg = await coro
            done += 1
            if success:
                ok += 1
            level = logging.INFO if success else logging.ERROR
            logger.log(level, "[%d/%d] %s", done, len(rows), msg)

        elapsed = (datetime.now() - started).total_seconds()
        logger.info(
            "done: %d/%d succeeded in %.1fs (%.1fs/row)",
            ok, len(rows), elapsed, elapsed / max(len(rows), 1),
        )
        return 0 if ok == len(rows) else 1
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill empty HouseView AI content.")
    parser.add_argument("--dry-run", action="store_true", help="list targets without calling Azure")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of rows processed")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run, limit=args.limit)))
