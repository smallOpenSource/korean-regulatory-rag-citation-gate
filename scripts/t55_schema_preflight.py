#!/usr/bin/env python3
"""T55 schema preflight report for live-provider readiness.

The script is intentionally read-only. It validates local SQL_ID migration files,
checks the active PostgreSQL schema with raw SQL, verifies Redis reachability, and
writes a secret-free JSON report under ``.omx/reports/t55`` by default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import RedisConfig  # noqa: E402
from apps.api.harness.core.redis_client import (  # noqa: E402
    acquire_lock,
    create_redis_client,
    release_lock,
)
from db.migrator import (  # noqa: E402
    database_url_from_env,
    discover_migrations,
    load_env_file,
    split_sql_statements,
    validate_statement,
)

REQUIRED_PROVIDER_MIGRATIONS = (12, 13, 14, 15, 16, 17, 18)
REQUIRED_TABLES = (
    "migration_versions",
    "source_licenses",
    "market_price_bars",
    "market_data_quality_checks",
    "macro_indicators",
    "raw_documents",
    "document_sources",
    "document_chunks",
    "batch_provider_evidence",
)

TABLE_STATUS_SQL = """
/* sql_id: t55_schema_table_status */
WITH required_tables(table_name) AS (
    VALUES
        ('migration_versions'),
        ('source_licenses'),
        ('market_price_bars'),
        ('market_data_quality_checks'),
        ('macro_indicators'),
        ('raw_documents'),
        ('document_sources'),
        ('document_chunks'),
        ('batch_provider_evidence')
)
SELECT table_name,
       (to_regclass('public.' || table_name) IS NOT NULL) AS present
FROM required_tables
ORDER BY table_name;
"""

MIGRATION_STATUS_SQL = """
/* sql_id: t55_schema_migration_status */
WITH required_versions(version) AS (
    VALUES (12), (13), (14), (15), (16), (17), (18)
)
SELECT required_versions.version,
       migration_versions.name,
       migration_versions.applied_at,
       (migration_versions.version IS NOT NULL) AS applied
FROM required_versions
LEFT JOIN migration_versions ON migration_versions.version = required_versions.version
ORDER BY required_versions.version;
"""

COLUMN_STATUS_SQL = """
/* sql_id: t55_schema_column_status */
WITH required_columns(table_name, column_name) AS (
    VALUES
        ('batch_provider_evidence', 'provider_code'),
        ('batch_provider_evidence', 'provider_status_code'),
        ('batch_provider_evidence', 'rows_collected'),
        ('batch_provider_evidence', 'target_ref'),
        ('batch_provider_evidence', 'provider_detail_json'),
        ('market_price_bars', 'source_code'),
        ('market_price_bars', 'source_as_of'),
        ('market_price_bars', 'quality_status_code'),
        ('document_sources', 'provider_code'),
        ('document_sources', 'receipt_no'),
        ('document_chunks', 'provider_code'),
        ('document_chunks', 'is_embedded'),
        ('macro_indicators', 'source_code')
)
SELECT required_columns.table_name,
       required_columns.column_name,
       (pg_attribute.attname IS NOT NULL) AS present
FROM required_columns
LEFT JOIN pg_class
  ON pg_class.oid = to_regclass('public.' || required_columns.table_name)
LEFT JOIN pg_attribute
  ON pg_attribute.attrelid = pg_class.oid
 AND pg_attribute.attname = required_columns.column_name
 AND pg_attribute.attisdropped IS FALSE
ORDER BY required_columns.table_name, required_columns.column_name;
"""

CONSTRAINT_STATUS_SQL = """
/* sql_id: t55_schema_constraint_status */
SELECT pg_class.relname AS table_name,
       pg_constraint.conname AS constraint_name,
       pg_get_constraintdef(pg_constraint.oid) AS constraint_definition
FROM pg_constraint
JOIN pg_class ON pg_class.oid = pg_constraint.conrelid
WHERE pg_class.relname IN (
    'batch_provider_evidence',
    'market_price_bars',
    'source_licenses',
    'document_sources'
)
ORDER BY pg_class.relname, pg_constraint.conname;
"""

EVIDENCE_COUNTS_SQL = """
/* sql_id: t55_schema_evidence_counts */
SELECT
    (SELECT count(*)::integer FROM batch_provider_evidence) AS provider_evidence_rows,
    (
        SELECT count(*)::integer
        FROM batch_provider_evidence
        WHERE provider_code = 'ECOS'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
    ) AS ecos_done_evidence_rows,
    (
        SELECT count(*)::integer
        FROM macro_indicators
        WHERE source_code = 'ECOS'
    ) AS ecos_parseable_rows,
    (
        SELECT count(*)::integer
        FROM batch_provider_evidence
        WHERE provider_code IN ('DART', 'OPENDART')
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
    ) AS dart_done_evidence_rows,
    (
        SELECT count(*)::integer
        FROM raw_documents
        WHERE source_type_code = 'DART'
    ) AS dart_raw_documents,
    (
        SELECT count(*)::integer
        FROM document_sources
        WHERE provider_code = 'DART'
    ) AS dart_document_sources,
    (
        SELECT count(*)::integer
        FROM document_chunks
        WHERE provider_code = 'DART'
    ) AS dart_document_chunks,
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE source_code IN ('KRX', 'PYKRX')
    ) AS krx_family_price_bar_rows,
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE source_code = 'KRX'
          AND is_synthetic IS FALSE
    ) AS official_krx_price_bar_rows,
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE source_code = 'PYKRX'
          AND is_synthetic IS FALSE
    ) AS pykrx_price_bar_rows,
    (
        SELECT count(DISTINCT price_date)::integer
        FROM market_price_bars
        WHERE source_code = 'KRX'
          AND is_synthetic IS FALSE
    ) AS official_krx_trading_day_count,
    (
        SELECT count(DISTINCT price_date)::integer
        FROM market_price_bars
        WHERE source_code = 'PYKRX'
          AND is_synthetic IS FALSE
    ) AS pykrx_trading_day_count,
    (
        SELECT count(*)::integer
        FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
          AND provider_detail_json->>'source_policy_code' = 'OFFICIAL_KRX_APPROVED'
    ) AS official_krx_policy_evidence_rows,
    (
        SELECT count(*)::integer
        FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
          AND provider_detail_json->>'source_policy_code' = 'PYKRX_AUXILIARY_APPROVED'
    ) AS pykrx_auxiliary_policy_evidence_rows;
"""


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def redacted_postgres_endpoint(database_url: str) -> dict[str, Any]:
    parsed = urlsplit(database_url)
    return {
        "scheme": parsed.scheme,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "database": parsed.path.lstrip("/") or None,
        "username_configured": bool(parsed.username),
    }


def redis_endpoint_summary() -> dict[str, Any]:
    sentinel_hosts = os.getenv("REDIS_SENTINEL_HOSTS", "").strip()
    sentinel_service = os.getenv("REDIS_SENTINEL_SERVICE_NAME", "").strip()
    redis_url = os.getenv("REDIS_URL", "").strip()
    if sentinel_hosts and sentinel_service:
        return {
            "mode": "sentinel",
            "sentinel_host_count": len([item for item in sentinel_hosts.split(",") if item]),
            "sentinel_service_name": sentinel_service,
            "db": int(os.getenv("REDIS_DB", "0") or "0"),
        }
    if redis_url:
        parsed = urlsplit(redis_url)
        return {
            "mode": "url",
            "scheme": parsed.scheme,
            "hostname": parsed.hostname,
            "port": parsed.port,
            "db": parsed.path.lstrip("/") or None,
        }
    return {
        "mode": "direct" if os.getenv("REDIS_HOST", "").strip() else "missing",
        "hostname": os.getenv("REDIS_HOST") or None,
        "port": int(os.getenv("REDIS_PORT", "6379") or "6379")
        if os.getenv("REDIS_HOST")
        else None,
        "db": int(os.getenv("REDIS_DB", "0") or "0"),
    }


def redis_config_from_env() -> RedisConfig:
    return RedisConfig(
        redis_url=os.getenv("REDIS_URL") or None,
        sentinel_hosts=os.getenv("REDIS_SENTINEL_HOSTS") or None,
        sentinel_service_name=os.getenv("REDIS_SENTINEL_SERVICE_NAME") or None,
        host=os.getenv("REDIS_HOST") or None,
        port=int(os.getenv("REDIS_PORT", "6379")) if os.getenv("REDIS_HOST") else None,
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0") or "0"),
        socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5") or "5"),
        socket_connect_timeout=float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5") or "5"),
        max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20") or "20"),
    )


def validate_local_sql_id_scan() -> dict[str, Any]:
    errors: list[str] = []
    statement_count = 0
    migrations = discover_migrations()
    for migration in migrations:
        statements = split_sql_statements(migration.path.read_text())
        for index, statement in enumerate(statements, start=1):
            statement_count += 1
            try:
                validate_statement(statement, context=f"{migration.path.name}:{index}")
            except RuntimeError as exc:
                errors.append(str(exc))
    return {
        "status_code": "READY" if not errors else "BLOCKED",
        "migration_count": len(migrations),
        "statement_count": statement_count,
        "errors": errors,
    }


def rows_to_dicts(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


async def collect_postgres_evidence() -> dict[str, Any]:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - environment boundary
        return {"status_code": "BLOCKED", "reason_class": exc.__class__.__name__}

    try:
        database_url = database_url_from_env()
    except RuntimeError as exc:
        return {"status_code": "BLOCKED", "reason_class": exc.__class__.__name__}

    evidence: dict[str, Any] = {
        "status_code": "BLOCKED",
        "endpoint": redacted_postgres_endpoint(database_url),
    }
    try:
        connection = await asyncpg.connect(database_url)
    except Exception as exc:  # noqa: BLE001 - report only sanitized class
        evidence["reason_class"] = exc.__class__.__name__
        return evidence

    try:
        table_rows = rows_to_dicts(await connection.fetch(TABLE_STATUS_SQL))
        evidence["required_tables"] = table_rows
        table_present = {row["table_name"]: bool(row["present"]) for row in table_rows}
        if table_present.get("migration_versions"):
            evidence["required_migrations"] = rows_to_dicts(
                await connection.fetch(MIGRATION_STATUS_SQL)
            )
        else:
            evidence["required_migrations"] = [
                {"version": version, "name": None, "applied_at": None, "applied": False}
                for version in REQUIRED_PROVIDER_MIGRATIONS
            ]
        evidence["required_columns"] = rows_to_dicts(await connection.fetch(COLUMN_STATUS_SQL))
        evidence["constraints"] = rows_to_dicts(await connection.fetch(CONSTRAINT_STATUS_SQL))

        if all(table_present.get(table_name) for table_name in REQUIRED_TABLES):
            counts_row = await connection.fetchrow(EVIDENCE_COUNTS_SQL)
            evidence["provider_evidence_counts"] = dict(counts_row) if counts_row else {}
        else:
            evidence["provider_evidence_counts"] = {}

        migrations_ready = all(row["applied"] for row in evidence["required_migrations"])
        tables_ready = all(table_present.get(table_name) for table_name in REQUIRED_TABLES)
        columns_ready = all(row["present"] for row in evidence["required_columns"])
        evidence["status_code"] = (
            "READY" if migrations_ready and tables_ready and columns_ready else "BLOCKED"
        )
        return evidence
    finally:
        await connection.close()


def collect_redis_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "status_code": "BLOCKED",
        "endpoint": redis_endpoint_summary(),
    }
    try:
        client = create_redis_client(redis_config_from_env())
        client.ping()
        evidence["ping_status_code"] = "READY"
        lock_key = f"harness:t55_schema_preflight:{utc_timestamp()}"
        lock = acquire_lock(
            client,
            key=lock_key,
            ttl_seconds=30,
            owner="t55-schema-preflight",
        )
        if lock is None:
            evidence["lock_smoke"] = {
                "status_code": "BLOCKED",
                "key": lock_key,
                "acquired": False,
                "released": False,
            }
            evidence["reason_class"] = "RedisLockUnavailable"
            return evidence
        released = release_lock(client, lock)
        evidence["lock_smoke"] = {
            "status_code": "READY" if released else "BLOCKED",
            "key": lock_key,
            "acquired": True,
            "released": released,
        }
        if not released:
            evidence["reason_class"] = "RedisLockReleaseFailed"
            return evidence
    except Exception as exc:  # noqa: BLE001 - report only sanitized class
        evidence["reason_class"] = exc.__class__.__name__
        return evidence
    evidence["status_code"] = "READY"
    return evidence


async def build_report() -> dict[str, Any]:
    sql_id_scan = validate_local_sql_id_scan()
    local_migrations = [
        {
            "version": migration.version,
            "name": migration.name,
            "path": str(migration.path.relative_to(PROJECT_ROOT)),
        }
        for migration in discover_migrations()
        if migration.version in REQUIRED_PROVIDER_MIGRATIONS
    ]
    postgres = await collect_postgres_evidence()
    redis = collect_redis_evidence()
    status_code = (
        "READY"
        if sql_id_scan["status_code"] == "READY"
        and postgres.get("status_code") == "READY"
        and redis.get("status_code") == "READY"
        else "BLOCKED"
    )
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status_code": status_code,
        "required_provider_migrations": local_migrations,
        "sql_id_scan": sql_id_scan,
        "postgres": postgres,
        "redis": redis,
        "notes": [
            "Report is read-only and secret-free.",
            "Provider rows are counted only when persisted in live provider tables.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="dotenv file to source before connecting (default: .env)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="output JSON path (default: .omx/reports/t55/schema-preflight-<ts>.json)",
    )
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    report = await build_report()
    report_path = args.report or (
        PROJECT_ROOT / ".omx" / "reports" / "t55" / f"schema-preflight-{utc_timestamp()}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"schema_preflight_report={report_path} status={report['status_code']}")
    return 0 if report["status_code"] == "READY" else 2


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
