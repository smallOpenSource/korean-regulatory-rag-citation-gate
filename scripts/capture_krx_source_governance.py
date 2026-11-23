#!/usr/bin/env python3
"""Capture canonical KRX source-governance evidence without leaking secrets.

The script performs live, read-only official KRX OpenAPI probes. It writes a
 timestamped governance artifact for both pass and fail-closed outcomes and
refreshes ``krx-source-governance-latest.json`` with that real outcome so a
stale passing artifact cannot mask a current live-source blocker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import load_env_file  # noqa: E402
from apps.api.harness.core.logging import redact_mapping, redact_secret_text  # noqa: E402
from apps.api.harness.external.http import (  # noqa: E402
    ExternalProviderError,
    JsonHttpResponse,
    build_url,
    request_json,
)
from apps.api.harness.external.public_data import KrxOfficialClient  # noqa: E402

OFFICIAL_KRX_POLICY_CODE = "OFFICIAL_KRX_APPROVED"
OFFICIAL_KRX_SOURCE_CODE = "KRX"
DEFAULT_REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"
DEFAULT_LATEST_PATH = DEFAULT_REPORT_DIR / "krx-source-governance-latest.json"
SUCCESS_HTTP_STATUSES = {200, 204}
RequestJson = Callable[..., JsonHttpResponse]


@dataclass(frozen=True)
class GovernanceCaptureResult:
    """Paths and payload emitted by one KRX source-governance capture."""

    report: dict[str, Any]
    artifact_path: Path
    latest_path: Path
    latest_refreshed: bool


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp_slug(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    os.replace(temporary, path)


def bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def csv_env(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


def parse_env_date(name: str, *, default: date) -> date:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    compact = raw.replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        raise ValueError(f"{name} must be YYYY-MM-DD or YYYYMMDD")
    return date(int(compact[:4]), int(compact[4:6]), int(compact[6:]))


def latest_weekday(today: date) -> date:
    candidate = today
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def redacted_hash(payload: Any) -> str:
    redacted_payload = redact_mapping(payload) if isinstance(payload, dict) else payload
    text = json.dumps(redacted_payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(text.encode("utf-8")).hexdigest()


def outblock_rows(payload: dict[str, Any]) -> list[Any]:
    for key in ("OutBlock_1", "outBlock_1", "output", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def classify_provider_error(message: str) -> str:
    lowered = message.lower()
    if "401" in lowered or "403" in lowered or "auth" in lowered or "key" in lowered:
        return "PROVIDER_FAILED_AUTH"
    if "429" in lowered or "rate" in lowered or "throttle" in lowered:
        return "PROVIDER_FAILED_RATE_LIMIT"
    if "invalid json" in lowered or "schema" in lowered:
        return "PROVIDER_FAILED_SCHEMA"
    return "PROVIDER_FAILED_NETWORK"


def build_endpoint_probe(
    *,
    base_url: str,
    api_key: str,
    path: str,
    market: str,
    bas_dd: str,
    timeout_seconds: float,
    requester: RequestJson = request_json,
) -> dict[str, Any]:
    url = build_url(base_url, path, {"basDd": bas_dd})
    try:
        response = requester(
            method="GET",
            url=url,
            headers={"AUTH_KEY": api_key},
            timeout_seconds=timeout_seconds,
        )
        rows = outblock_rows(response.payload)
        return {
            "path": path,
            "market": market,
            "probe_date": bas_dd,
            "http_status": response.status_code,
            "provider_status_code": "PROVIDER_DONE",
            "returned_row_count": len(rows),
            "evidence_hash": redacted_hash(response.payload),
            "redacted_evidence_hash": redacted_hash({"rows": rows[:5]}),
            "redacted_auth": True,
        }
    except ExternalProviderError as exc:
        reason = redact_secret_text(str(exc))
        return {
            "path": path,
            "market": market,
            "probe_date": bas_dd,
            "http_status": None,
            "provider_status_code": classify_provider_error(reason),
            "returned_row_count": 0,
            "evidence_hash": redacted_hash({"error": reason}),
            "redacted_auth": True,
            "reason_message": reason,
        }


def validate_required_policy() -> list[str]:
    errors: list[str] = []
    if not bool_env("HARNESS_BATCH_KRX_ENABLED"):
        errors.append("HARNESS_BATCH_KRX_ENABLED must be true for official KRX governance")
    if os.getenv("HARNESS_BATCH_KRX_SOURCE", "").strip().upper() != OFFICIAL_KRX_SOURCE_CODE:
        errors.append("HARNESS_BATCH_KRX_SOURCE must be KRX")
    if os.getenv("HARNESS_BATCH_KRX_POLICY", "").strip().upper() != OFFICIAL_KRX_POLICY_CODE:
        errors.append("HARNESS_BATCH_KRX_POLICY must be OFFICIAL_KRX_APPROVED")
    if not os.getenv("KRX_API_BASE_URL", "").strip():
        errors.append("KRX_API_BASE_URL is required")
    if not os.getenv("KRX_API_KEY", "").strip():
        errors.append("KRX_API_KEY is required")
    return errors


def build_report(
    args: argparse.Namespace,
    *,
    now: datetime,
    requester: RequestJson = request_json,
    markets_override: tuple[str, ...] | None = None,
    probe_date_override: str | None = None,
) -> dict[str, Any]:
    load_env_file(args.env_file)
    errors = validate_required_policy()
    base_url = os.getenv("KRX_API_BASE_URL", "").strip()
    api_key = os.getenv("KRX_API_KEY", "").strip()
    timeout_seconds = float(os.getenv("KRX_API_TIMEOUT_SECONDS", "20"))
    probe_date = (
        date(
            int(probe_date_override[:4]),
            int(probe_date_override[4:6]),
            int(probe_date_override[6:]),
        )
        if probe_date_override and len(probe_date_override) == 8 and probe_date_override.isdigit()
        else parse_env_date(
            "HARNESS_BATCH_KRX_END_DATE",
            default=latest_weekday(now.date()),
        )
    )
    bas_dd = compact_date(probe_date)
    markets = markets_override or csv_env(
        "HARNESS_BATCH_KRX_UNIVERSE_MARKETS",
        default=csv_env("HARNESS_BATCH_KRX_MARKETS", default=("KOSPI", "KOSDAQ")),
    )
    endpoint_map = KrxOfficialClient.DAILY_TRADING_PATHS
    endpoints: list[dict[str, Any]] = []
    if not errors:
        for market in markets:
            path = endpoint_map.get(market)
            if path is None:
                endpoints.append(
                    {
                        "path": None,
                        "market": market,
                        "probe_date": bas_dd,
                        "http_status": None,
                        "provider_status_code": "PROVIDER_FAILED_SCHEMA",
                        "returned_row_count": 0,
                        "evidence_hash": redacted_hash({"unsupported_market": market}),
                        "redacted_auth": True,
                        "reason_message": f"Unsupported KRX market code: {market}",
                    }
                )
                continue
            endpoints.append(
                build_endpoint_probe(
                    base_url=base_url,
                    api_key=api_key,
                    path=path,
                    market=market,
                    bas_dd=bas_dd,
                    timeout_seconds=timeout_seconds,
                    requester=requester,
                )
            )

    successful_endpoints = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("http_status") in SUCCESS_HTTP_STATUSES
        and int(endpoint.get("returned_row_count") or 0) > 0
    ]
    if not successful_endpoints and not errors:
        errors.append("at least one official KRX endpoint must return real rows")

    passed = not errors and bool(successful_endpoints)
    return {
        "schema_version": "1.0",
        "artifact_kind": "krx_source_governance",
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "checked_by": "scripts/capture_krx_source_governance.py",
        "source_name": "KRX official OpenAPI",
        "source_code": OFFICIAL_KRX_SOURCE_CODE,
        "source_policy_code": OFFICIAL_KRX_POLICY_CODE,
        "authorization_status": "APPROVED" if passed else "BLOCKED",
        "secret_redacted": True,
        "key_env_name": "KRX_API_KEY",
        "api_base_url_host": urlsplit(base_url).netloc if base_url else None,
        "operational_owner": os.getenv("HARNESS_BATCH_OWNER", "data-platform"),
        "approved_use_summary": "local serviceable top-200/30-day readiness verification",
        "approved_until": None,
        "rate_limit_policy": "bounded live governance probe; no raw provider payload persisted",
        "terms_reference": os.getenv("HARNESS_BATCH_KRX_TERMS_REFERENCE", "internal runbook"),
        "failure_mode": "fail_closed",
        "probe_date": bas_dd,
        "markets": list(markets),
        "endpoints": endpoints,
        "errors": errors,
        "passed": passed,
    }


def capture_krx_source_governance(
    *,
    env_file: Path,
    output_dir: Path = DEFAULT_REPORT_DIR,
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    probe_date: str | None = None,
    requester: RequestJson = request_json,
    latest_name: str = "krx-source-governance-latest.json",
) -> GovernanceCaptureResult:
    """Capture source-governance evidence and refresh canonical latest fail-closed.

    ``latest`` is intentionally refreshed for both APPROVED and BLOCKED outcomes
    so stale green evidence cannot mask a current official KRX blocker.
    """

    now = utc_now()
    args = argparse.Namespace(env_file=env_file)
    report = build_report(
        args,
        now=now,
        requester=requester,
        markets_override=markets,
        probe_date_override=probe_date,
    )
    artifact_path = output_dir / f"krx-source-governance-{timestamp_slug(now)}.json"
    latest_path = output_dir / latest_name
    atomic_write_json(artifact_path, report)
    atomic_write_json(latest_path, report | {"canonical_latest_source": str(artifact_path)})
    return GovernanceCaptureResult(
        report=report,
        artifact_path=artifact_path,
        latest_path=latest_path,
        latest_refreshed=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--latest", type=Path, default=DEFAULT_LATEST_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = utc_now()
    output = args.output or DEFAULT_REPORT_DIR / f"krx-source-governance-{timestamp_slug(now)}.json"
    report = build_report(args, now=now)
    atomic_write_json(output, report)
    atomic_write_json(args.latest, report | {"canonical_latest_source": str(output)})
    print(json.dumps({"ok": report["passed"], "output": str(output), "latest": str(args.latest)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
