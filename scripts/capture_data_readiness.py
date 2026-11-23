#!/usr/bin/env python3
"""Capture the DB-backed ``/data/readiness`` payload into canonical evidence files."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import (  # noqa: E402
    DatabaseConfig,
    database_url_from_env,
    load_env_file,
)
from apps.api.harness.core.db import create_pool  # noqa: E402
from apps.api.harness.core.logging import redact_secret_text  # noqa: E402
from apps.api.harness.repositories.readiness import get_data_readiness  # noqa: E402

DEFAULT_REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"
DEFAULT_LATEST_PATH = DEFAULT_REPORT_DIR / "data-readiness-latest.json"
SERVICEABLE_UNIVERSE_CODE = "DOMESTIC_TOP200_MARKET_CAP"


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp_slug(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    os.replace(temporary, path)


def blocked_top200_coverage(reason_message: str) -> dict[str, Any]:
    return {
        "universe_code": SERVICEABLE_UNIVERSE_CODE,
        "source_code": "KRX",
        "source_policy_code": "OFFICIAL_KRX_APPROVED",
        "selected_count": 0,
        "required_count": 200,
        "expected_member_days": 0,
        "observed_member_days": 0,
        "covered_tickers": 0,
        "coverage_ratio": 0.0,
        "missing_member_days": 0,
        "status_code": "BLOCKED",
        "blocking_reasons": [reason_message],
    }


def build_blocked_capture(
    *,
    now: datetime,
    reason_class: str,
    reason_message: str,
) -> dict[str, Any]:
    top200 = blocked_top200_coverage(reason_message)
    readiness = {
        "status_code": "BLOCKED",
        "domestic_market": {
            "status_code": "BLOCKED",
            "top200_coverage": top200,
            "checks": [
                {
                    "check_code": "market.top200_universe",
                    "status_code": "BLOCKED",
                    "message": reason_message,
                    "source_code": "KRX",
                    "source_policy_code": "OFFICIAL_KRX_APPROVED",
                },
                {
                    "check_code": "market.top200_30d_coverage",
                    "status_code": "BLOCKED",
                    "message": reason_message,
                    "source_code": "KRX",
                    "source_policy_code": "OFFICIAL_KRX_APPROVED",
                },
            ],
        },
        "checks": [
            {
                "check_code": "provider.dart_parseable_documents",
                "status_code": "BLOCKED",
                "message": "OpenDART lineage cannot be verified while PostgreSQL is unavailable.",
            },
            {
                "check_code": "provider.ecos_parseable_rows",
                "status_code": "BLOCKED",
                "message": "ECOS lineage cannot be verified while PostgreSQL is unavailable.",
            },
        ],
    }
    return {
        "schema_version": "1.0",
        "artifact_kind": "data_readiness_capture",
        "capture_status_code": "BLOCKED",
        "captured_at": now.isoformat().replace("+00:00", "Z"),
        "captured_by": "scripts/capture_data_readiness.py",
        "readiness": readiness,
        "capture_error": {
            "stage": "postgres-read",
            "reason_class": reason_class,
            "reason_message": reason_message,
        },
        "errors": [f"PostgreSQL readiness capture failed: {reason_message}"],
        **readiness,
    }


async def capture(args: argparse.Namespace, *, now: datetime) -> dict[str, Any]:
    load_env_file(args.env_file)
    try:
        pool = await create_pool(DatabaseConfig(database_url_from_env()), min_size=1, max_size=1)
        try:
            async with pool.acquire() as connection:
                readiness = await get_data_readiness(connection)
        finally:
            await pool.close()
    except Exception as exc:  # noqa: BLE001 - write BLOCKED canonical latest instead of going absent
        return build_blocked_capture(
            now=now,
            reason_class=exc.__class__.__name__,
            reason_message=redact_secret_text(str(exc)),
        )
    return {
        "schema_version": "1.0",
        "artifact_kind": "data_readiness_capture",
        "capture_status_code": "READY",
        "captured_at": now.isoformat().replace("+00:00", "Z"),
        "captured_by": "scripts/capture_data_readiness.py",
        "readiness": readiness,
        **readiness,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--latest", type=Path, default=DEFAULT_LATEST_PATH)
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    now = utc_now()
    output = args.output or DEFAULT_REPORT_DIR / f"data-readiness-{timestamp_slug(now)}.json"
    payload = await capture(args, now=now)
    atomic_write_json(output, payload)
    atomic_write_json(args.latest, payload | {"canonical_latest_source": str(output)})
    ok = payload.get("capture_status_code") == "READY"
    print(json.dumps({"ok": ok, "output": str(output), "latest": str(args.latest)}))
    return 0 if ok else 1


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
