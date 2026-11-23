#!/usr/bin/env python3
"""Capture canonical serviceable top-200/30-day batch evidence from live stores.

The script is read-only after the batch run: it queries PostgreSQL with SQL_ID
statements, verifies Redis reachability/lock semantics, and emits a canonical
artifact consumed by ``scripts/verify_serviceable_readiness.py``. It never
creates provider rows and never marks missing evidence as READY.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import (  # noqa: E402
    DatabaseConfig,
    RedisConfig,
    database_url_from_env,
    load_env_file,
    optional_float,
    optional_int,
)
from apps.api.harness.core.db import create_pool, fetch_all, fetch_one  # noqa: E402
from apps.api.harness.core.logging import redact_secret_text  # noqa: E402
from apps.api.harness.core.redis_client import (  # noqa: E402
    RedisUnavailableError,
    acquire_lock,
    create_redis_client,
    release_lock,
)

OFFICIAL_KRX_POLICY_CODE = "OFFICIAL_KRX_APPROVED"
OFFICIAL_KRX_SOURCE_CODE = "KRX"
SERVICEABLE_UNIVERSE_CODE = "DOMESTIC_TOP200_MARKET_CAP"
DEFAULT_REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"
DEFAULT_LATEST_PATH = DEFAULT_REPORT_DIR / "serviceable-top200-30d-latest.json"

POSTGRES_VERSION_SQL = """
/* sql_id: capture_serviceable_postgres_version */
SELECT current_setting('server_version') AS server_version;
"""

TOP200_COVERAGE_SQL = """
/* sql_id: capture_serviceable_top200_30d_coverage */
WITH latest_snapshot AS (
    SELECT id, universe_code, as_of_date, resolved_trading_date, source_code,
           source_policy_code, target_size, selected_count, raw_candidate_count,
           excluded_count, coverage_status_code, provider_evidence_id, created_at
    FROM market_universe_snapshots
    WHERE universe_code = $1::varchar
      AND source_code = 'KRX'
      AND source_policy_code = 'OFFICIAL_KRX_APPROVED'
    ORDER BY as_of_date DESC, resolved_trading_date DESC, created_at DESC
    LIMIT 1
), coverage AS (
    SELECT count(*) FILTER (WHERE daily.is_expected_trading_day IS TRUE)::integer
               AS expected_member_days,
           count(*) FILTER (
               WHERE daily.is_expected_trading_day IS TRUE AND daily.has_valid_bar IS TRUE
           )::integer AS observed_member_days,
           count(*) FILTER (
               WHERE daily.is_expected_trading_day IS TRUE AND daily.has_valid_bar IS FALSE
           )::integer AS missing_member_days,
           count(DISTINCT daily.security_id) FILTER (
               WHERE daily.is_expected_trading_day IS TRUE AND daily.has_valid_bar IS TRUE
           )::integer AS covered_tickers,
           max(bar.source_as_of) AS latest_source_as_of
    FROM market_universe_coverage_daily daily
    JOIN latest_snapshot ON latest_snapshot.id = daily.snapshot_id
    LEFT JOIN market_price_bars bar ON bar.id = daily.market_price_bar_id
), market_days AS (
    SELECT COALESCE(
        jsonb_object_agg(market_code, expected_trading_days ORDER BY market_code),
        '{}'::jsonb
    ) AS expected_trading_days_by_market
    FROM (
        SELECT daily.market_code,
               count(DISTINCT daily.calendar_date) FILTER (
                   WHERE daily.is_expected_trading_day IS TRUE
               )::integer AS expected_trading_days
        FROM market_universe_coverage_daily daily
        JOIN latest_snapshot ON latest_snapshot.id = daily.snapshot_id
        GROUP BY daily.market_code
    ) by_market
)
SELECT latest_snapshot.id AS snapshot_id,
       latest_snapshot.universe_code,
       latest_snapshot.as_of_date,
       latest_snapshot.resolved_trading_date,
       latest_snapshot.source_code,
       latest_snapshot.source_policy_code,
       latest_snapshot.target_size,
       latest_snapshot.selected_count,
       latest_snapshot.raw_candidate_count,
       latest_snapshot.excluded_count,
       latest_snapshot.coverage_status_code,
       latest_snapshot.provider_evidence_id,
       latest_snapshot.created_at AS snapshot_created_at,
       COALESCE(coverage.expected_member_days, 0) AS expected_member_days,
       COALESCE(coverage.observed_member_days, 0) AS observed_member_days,
       COALESCE(coverage.missing_member_days, 0) AS missing_member_days,
       COALESCE(coverage.covered_tickers, 0) AS covered_tickers,
       CASE
           WHEN COALESCE(coverage.expected_member_days, 0) = 0 THEN 0::numeric
           ELSE COALESCE(coverage.observed_member_days, 0)::numeric
                / coverage.expected_member_days::numeric
       END AS coverage_ratio,
       coverage.latest_source_as_of,
       COALESCE(market_days.expected_trading_days_by_market, '{}'::jsonb)
           AS expected_trading_days_by_market
FROM latest_snapshot
LEFT JOIN coverage ON TRUE
LEFT JOIN market_days ON TRUE;
"""

PROVIDER_LINEAGE_SQL = """
/* sql_id: capture_serviceable_provider_lineage */
SELECT provider_code, provider_status_code, target_ref, rows_collected, rows_skipped,
       rows_failed, reason_message, provider_detail_json, observed_at
FROM batch_provider_evidence
WHERE provider_code IN ('KRX', 'DART', 'OPENDART', 'ECOS')
ORDER BY CASE provider_code
             WHEN 'ECOS' THEN 1
             WHEN 'DART' THEN 2
             WHEN 'OPENDART' THEN 3
             WHEN 'KRX' THEN 4
             ELSE 5
         END,
         observed_at DESC,
         target_ref
LIMIT 500;
"""

SYNTHETIC_PROVIDER_ROW_SQL = """
/* sql_id: capture_serviceable_synthetic_provider_rows */
SELECT count(*)::integer AS synthetic_provider_rows
FROM market_price_bars
WHERE source_code = 'KRX'
  AND is_synthetic IS TRUE;
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp_slug(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    os.replace(temporary, path)


def redis_config_from_env() -> RedisConfig:
    return RedisConfig(
        redis_url=os.getenv("REDIS_URL") or None,
        sentinel_hosts=os.getenv("REDIS_SENTINEL_HOSTS") or None,
        sentinel_service_name=os.getenv("REDIS_SENTINEL_SERVICE_NAME") or None,
        host=os.getenv("REDIS_HOST") or None,
        port=optional_int("REDIS_PORT", 6379) if os.getenv("REDIS_HOST") else None,
        password=os.getenv("REDIS_PASSWORD") or None,
        db=optional_int("REDIS_DB", 0),
        socket_timeout=optional_float("REDIS_SOCKET_TIMEOUT", 5.0),
        socket_connect_timeout=optional_float("REDIS_SOCKET_CONNECT_TIMEOUT", 5.0),
        max_connections=optional_int("REDIS_MAX_CONNECTIONS", 20),
    )


def collect_redis_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "status_code": "BLOCKED",
        "ping": False,
        "lock_acquired": False,
        "lock_released": False,
    }
    client = None
    try:
        client = create_redis_client(redis_config_from_env())
        evidence["ping"] = bool(client.ping())
        lock = acquire_lock(
            client,
            key="harness:serviceable:top200_30d:canonical_capture",
            ttl_seconds=30,
        )
        evidence["lock_acquired"] = lock is not None
        evidence["lock_released"] = bool(release_lock(client, lock)) if lock else False
        evidence["status_code"] = (
            "READY"
            if evidence["ping"] and evidence["lock_acquired"] and evidence["lock_released"]
            else "BLOCKED"
        )
    except (RedisUnavailableError, Exception) as exc:  # noqa: BLE001 - report sanitized blocker
        evidence["reason_class"] = exc.__class__.__name__
        evidence["reason_message"] = redact_secret_text(str(exc))
    finally:
        if client is not None:
            client.close()
    return evidence


def normalize_row(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(value)


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def decimal_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)))


def coverage_payload(row: Mapping[str, Any] | None, *, universe_code: str) -> dict[str, Any]:
    if not row:
        return {
            "universe_code": universe_code,
            "source_code": OFFICIAL_KRX_SOURCE_CODE,
            "source_policy_code": OFFICIAL_KRX_POLICY_CODE,
            "selected_count": 0,
            "required_count": 200,
            "expected_member_days": 0,
            "observed_member_days": 0,
            "covered_tickers": 0,
            "coverage_ratio": 0.0,
            "missing_member_days": 0,
            "status_code": "BLOCKED",
            "blocking_reasons": ["No official KRX top-200 universe snapshot is persisted."],
        }
    expected_member_days = int_value(row.get("expected_member_days"))
    observed_member_days = int_value(row.get("observed_member_days"))
    missing_member_days = int_value(row.get("missing_member_days"))
    coverage_ratio = decimal_float(row.get("coverage_ratio"))
    selected_count = int_value(row.get("selected_count"))
    required_count = int_value(row.get("target_size")) or 200
    blocking_reasons: list[str] = []
    if selected_count < required_count:
        blocking_reasons.append(
            f"Selected universe count {selected_count} is below required {required_count}."
        )
    if expected_member_days <= 0:
        blocking_reasons.append("No official KRX expected member-day denominator is persisted.")
    if missing_member_days > 0:
        blocking_reasons.append(f"{missing_member_days} expected member-days are missing bars.")
    if expected_member_days > 0 and coverage_ratio < 1.0:
        blocking_reasons.append(f"Coverage ratio {coverage_ratio} is below required 1.0.")
    ready = (
        selected_count >= required_count
        and expected_member_days > 0
        and missing_member_days == 0
        and coverage_ratio >= 1.0
    )
    return {
        "universe_code": str(row.get("universe_code") or universe_code),
        "as_of_date": row.get("as_of_date"),
        "resolved_trading_date": row.get("resolved_trading_date"),
        "source_code": str(row.get("source_code") or OFFICIAL_KRX_SOURCE_CODE),
        "source_policy_code": str(row.get("source_policy_code") or OFFICIAL_KRX_POLICY_CODE),
        "selected_count": selected_count,
        "required_count": required_count,
        "expected_member_days": expected_member_days,
        "observed_member_days": observed_member_days,
        "covered_tickers": int_value(row.get("covered_tickers")),
        "coverage_ratio": coverage_ratio,
        "missing_member_days": missing_member_days,
        "latest_source_as_of": row.get("latest_source_as_of"),
        "expected_trading_days_by_market": row.get("expected_trading_days_by_market") or {},
        "snapshot_id": str(row.get("snapshot_id")) if row.get("snapshot_id") else None,
        "coverage_status_code": row.get("coverage_status_code"),
        "status_code": "READY" if ready else "BLOCKED",
        "blocking_reasons": blocking_reasons,
    }


def lineage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_provider: dict[str, dict[str, Any]] = {}
    for row in rows:
        provider = str(row.get("provider_code") or "UNKNOWN")
        item = by_provider.setdefault(
            provider,
            {
                "provider_code": provider,
                "ready_rows": 0,
                "latest_status_code": row.get("provider_status_code"),
                "latest_observed_at": row.get("observed_at"),
                "evidence": [],
            },
        )
        if row.get("provider_status_code") == "PROVIDER_DONE" and int_value(
            row.get("rows_collected")
        ) > 0:
            item["ready_rows"] += int_value(row.get("rows_collected"))
        if len(item["evidence"]) < 5:
            item["evidence"].append(row)
    return by_provider


def build_artifact(
    *,
    now: datetime,
    postgres_version: str | None,
    coverage_row: Mapping[str, Any] | None,
    provider_rows: list[dict[str, Any]],
    synthetic_provider_rows: int,
    redis: dict[str, Any],
    universe_code: str,
) -> dict[str, Any]:
    top200 = coverage_payload(coverage_row, universe_code=universe_code)
    errors: list[str] = []
    postgres_ready = bool(postgres_version and str(postgres_version).startswith("17."))
    if not postgres_ready:
        errors.append(f"PostgreSQL 17 is required; observed server_version={postgres_version!r}")
    if redis.get("status_code") != "READY":
        errors.append("Redis ping/lock readiness is required")
    if top200["status_code"] != "READY":
        errors.extend(str(reason) for reason in top200.get("blocking_reasons", []))
    if synthetic_provider_rows > 0:
        errors.append(f"KRX provider rows include synthetic rows: {synthetic_provider_rows}")
    provider_lineage = lineage_summary(provider_rows)
    opendart_ready = any(
        int_value((provider_lineage.get(provider) or {}).get("ready_rows")) > 0
        for provider in ("DART", "OPENDART")
    )
    if not opendart_ready:
        errors.append("OpenDART lineage evidence is missing")
    if int_value((provider_lineage.get("ECOS") or {}).get("ready_rows")) <= 0:
        errors.append("ECOS lineage evidence is missing")
    ready = not errors
    return {
        "schema_version": "1.0",
        "artifact_kind": "serviceable_top200_30d_batch",
        "captured_at": now.isoformat().replace("+00:00", "Z"),
        "captured_by": "scripts/capture_serviceable_top200_30d_artifact.py",
        "source_code": OFFICIAL_KRX_SOURCE_CODE,
        "source_policy_code": OFFICIAL_KRX_POLICY_CODE,
        "postgres": {
            "server_version": postgres_version,
            "required_major": 17,
            "status_code": "READY" if postgres_ready else "BLOCKED",
        },
        "redis": redis,
        "redis_ping": redis.get("ping") is True,
        "top200_coverage": top200,
        "serviceable_top200_30d": top200,
        "provider_lineage": provider_lineage,
        "provider_summary": {"is_synthetic": synthetic_provider_rows > 0},
        "synthetic_provider_row_count": synthetic_provider_rows,
        "no_fabricated_provider_rows": synthetic_provider_rows == 0,
        "sql_ids": [
            "capture_serviceable_postgres_version",
            "capture_serviceable_top200_30d_coverage",
            "capture_serviceable_provider_lineage",
            "capture_serviceable_synthetic_provider_rows",
        ],
        "status_code": "READY" if ready else "BLOCKED",
        "passed": ready,
        "errors": errors,
    }


async def capture(args: argparse.Namespace, *, now: datetime) -> dict[str, Any]:
    load_env_file(args.env_file)
    redis = collect_redis_evidence()
    try:
        pool = await create_pool(DatabaseConfig(database_url_from_env()), min_size=1, max_size=1)
        try:
            async with pool.acquire() as connection:
                postgres_row = normalize_row(await fetch_one(connection, POSTGRES_VERSION_SQL))
                coverage_row = normalize_row(
                    await fetch_one(connection, TOP200_COVERAGE_SQL, args.universe_code)
                )
                provider_rows = [
                    dict(row) for row in await fetch_all(connection, PROVIDER_LINEAGE_SQL)
                ]
                synthetic_row = normalize_row(
                    await fetch_one(connection, SYNTHETIC_PROVIDER_ROW_SQL)
                )
        finally:
            await pool.close()
    except Exception as exc:  # noqa: BLE001 - failed live stores still produce BLOCKED evidence
        reason_message = redact_secret_text(str(exc))
        artifact = build_artifact(
            now=now,
            postgres_version=None,
            coverage_row=None,
            provider_rows=[],
            synthetic_provider_rows=0,
            redis=redis,
            universe_code=args.universe_code,
        )
        artifact["capture_error"] = {
            "stage": "postgres-read",
            "reason_class": exc.__class__.__name__,
            "reason_message": reason_message,
        }
        artifact["errors"].append(f"PostgreSQL capture failed: {reason_message}")
        return artifact
    return build_artifact(
        now=now,
        postgres_version=postgres_row.get("server_version"),
        coverage_row=coverage_row,
        provider_rows=provider_rows,
        synthetic_provider_rows=int_value(synthetic_row.get("synthetic_provider_rows")),
        redis=redis,
        universe_code=args.universe_code,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--latest", type=Path, default=DEFAULT_LATEST_PATH)
    parser.add_argument("--universe-code", default=SERVICEABLE_UNIVERSE_CODE)
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    now = utc_now()
    output = args.output or (
        DEFAULT_REPORT_DIR / f"serviceable-top200-30d-{timestamp_slug(now)}.json"
    )
    artifact = await capture(args, now=now)
    atomic_write_json(output, artifact)
    atomic_write_json(args.latest, artifact | {"canonical_latest_source": str(output)})
    print(
        json.dumps(
            {"ok": artifact["passed"], "output": str(output), "latest": str(args.latest)},
            ensure_ascii=False,
        )
    )
    return 0 if artifact["passed"] else 1


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
