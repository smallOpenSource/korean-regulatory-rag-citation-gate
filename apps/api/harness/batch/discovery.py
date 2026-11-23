"""Read-only provider target discovery helpers.

The module performs safe provider GET/read calls and emits redacted target
catalog evidence. It does not persist rows, mutate local caches, or print API
keys. T55 uses the OpenDART path to prove that selected targets have both list
rows and downloadable ``document.xml`` bodies before the batch runner can claim
provider readiness.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.batch.providers import (  # noqa: E402
    DART_XML_PARSER_VERSION,
    DartFilingTarget,
    dart_list_evidence,
    ensure_dart_document_xml_success,
    parse_dart_corp_code_zip,
    parse_dart_filing_documents,
)
from apps.api.harness.core.config import load_env_file  # noqa: E402
from apps.api.harness.core.logging import redact_secret_text  # noqa: E402
from apps.api.harness.external.http import ExternalProviderError  # noqa: E402
from apps.api.harness.external.public_data import DartClient  # noqa: E402

DEFAULT_DART_DISCOVERY_STOCK_CODES: tuple[str, ...] = (
    "005930",  # Samsung Electronics
    "000660",  # SK hynix
    "035420",  # NAVER
    "005380",  # Hyundai Motor
    "068270",  # Celltrion
)
DART_DISCOVERY_WINDOWS_DAYS: tuple[int, ...] = (365, 180, 90, 30, 1)


@dataclass(frozen=True)
class DartDiscoveryWindow:
    """One rolling OpenDART search window."""

    lookback_days: int
    begin_date: str
    end_date: str


@dataclass(frozen=True)
class DartDiscoveryCandidate:
    """Non-secret OpenDART target proven by list.json plus document.xml."""

    stock_code: str | None
    corp_code: str
    begin_date: str
    end_date: str
    page_count: int
    receipt_no: str
    receipt_date: str | None
    report_name: str | None
    canonical_document_url: str
    parser_version: str = DART_XML_PARSER_VERSION


def compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def parse_compact_or_iso_date(value: str) -> date:
    clean = value.strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(clean, pattern).date()
        except ValueError:
            continue
    raise ValueError("date must be YYYY-MM-DD or YYYYMMDD")


def csv_values(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def build_dart_discovery_windows(
    *, today: date | None = None, lookback_days: tuple[int, ...] = DART_DISCOVERY_WINDOWS_DAYS
) -> tuple[DartDiscoveryWindow, ...]:
    """Return wide-to-narrow DART list windows before any one-day fallback."""

    end_date = today or date.today()
    return tuple(
        DartDiscoveryWindow(
            lookback_days=days,
            begin_date=compact_date(end_date - timedelta(days=days)),
            end_date=compact_date(end_date),
        )
        for days in lookback_days
    )


def dart_discovery_seed_targets(*, page_count: int = 100) -> tuple[DartFilingTarget, ...]:
    """Build read-only DART discovery seeds from env or locked default tickers."""

    stock_codes = csv_values(os.getenv("HARNESS_BATCH_DART_DISCOVERY_STOCK_CODES"))
    if not stock_codes:
        stock_codes = DEFAULT_DART_DISCOVERY_STOCK_CODES
    targets = []
    for stock_code in stock_codes:
        if not (stock_code.isdigit() and len(stock_code) == 6):
            raise ValueError("HARNESS_BATCH_DART_DISCOVERY_STOCK_CODES must be six-digit tickers")
        targets.append(
            DartFilingTarget(
                corp_code=None,
                stock_code=stock_code,
                begin_date="",
                end_date="",
                page_count=page_count,
            )
        )
    return tuple(targets)


def _filing_row_count(payload: dict[str, Any]) -> int:
    rows = payload.get("list")
    if isinstance(rows, dict):
        return 1
    if isinstance(rows, list):
        return len(rows)
    return 0


def _candidate_from_document(
    *,
    target: DartFilingTarget,
    corp_code: str,
    window: DartDiscoveryWindow,
    document: dict[str, Any],
    client: DartClient,
) -> DartDiscoveryCandidate:
    source_payload = document.get("source_payload") or {}
    return DartDiscoveryCandidate(
        stock_code=target.stock_code,
        corp_code=corp_code,
        begin_date=window.begin_date,
        end_date=window.end_date,
        page_count=target.page_count,
        receipt_no=str(document["receipt_no"]),
        receipt_date=str(source_payload.get("receipt_date") or "") or None,
        report_name=str(source_payload.get("report_name") or "") or None,
        canonical_document_url=client.canonical_document_url(
            receipt_no=str(document["receipt_no"])
        ),
    )


def discover_dart_targets(
    *, client: DartClient, today: date | None = None, max_targets: int = 2, page_count: int = 100
) -> dict[str, Any]:
    """Discover DART targets that have list rows and document.xml bodies.

    The returned payload is intentionally safe to persist as an operator report:
    it contains target metadata and canonical non-secret URLs only.
    """

    corp_code_by_stock = parse_dart_corp_code_zip(client.corp_code_zip())
    windows = build_dart_discovery_windows(today=today)
    candidates: list[DartDiscoveryCandidate] = []
    checks: list[dict[str, Any]] = []
    for target in dart_discovery_seed_targets(page_count=page_count):
        if len(candidates) >= max_targets:
            break
        corp_code = corp_code_by_stock.get(str(target.stock_code))
        if not corp_code:
            checks.append(
                {
                    "stock_code": target.stock_code,
                    "status_code": "PROVIDER_FAILED_SCHEMA",
                    "reason_message": "corpCode.xml did not map this stock_code",
                }
            )
            continue
        for window in windows:
            window_target = DartFilingTarget(
                corp_code=corp_code,
                stock_code=target.stock_code,
                begin_date=window.begin_date,
                end_date=window.end_date,
                page_count=target.page_count,
            )
            payload = client.list_filings(
                corp_code=corp_code,
                begin_date=window.begin_date,
                end_date=window.end_date,
                page_count=target.page_count,
            )
            list_evidence = dart_list_evidence(
                payload=payload,
                target=window_target,
                corp_code=corp_code,
                rows_collected=_filing_row_count(payload),
            )
            check = {
                "stock_code": target.stock_code,
                "corp_code": corp_code,
                "lookback_days": window.lookback_days,
                "provider_status_code": list_evidence.provider_status_code,
                "filing_rows": _filing_row_count(payload),
            }
            checks.append(check)
            if list_evidence.provider_status_code != "PROVIDER_DONE":
                continue
            for document in parse_dart_filing_documents(
                payload=payload, api_base_url=client.config.base_url
            ):
                xml_text = client.document_xml(receipt_no=str(document["receipt_no"]))
                if not ensure_dart_document_xml_success(
                    xml_text, receipt_no=str(document["receipt_no"])
                ):
                    continue
                candidate = _candidate_from_document(
                    target=target,
                    corp_code=corp_code,
                    window=window,
                    document=document,
                    client=client,
                )
                candidates.append(candidate)
                check["document_xml_status_code"] = "PROVIDER_DONE"
                check["receipt_no"] = candidate.receipt_no
                break
            if len(candidates) >= max_targets or any(
                candidate.stock_code == target.stock_code for candidate in candidates
            ):
                break
    status_code = "DONE" if candidates else "NO_DATA"
    return {
        "provider": "DART",
        "status_code": status_code,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "target_count": len(candidates),
        "targets_json": [
            {
                "stock_code": candidate.stock_code,
                "corp_code": candidate.corp_code,
                "begin_date": candidate.begin_date,
                "end_date": candidate.end_date,
                "page_count": candidate.page_count,
            }
            for candidate in candidates
        ],
        "candidates": [asdict(candidate) for candidate in candidates],
        "checks": checks,
        "windows": [asdict(window) for window in windows],
    }


def write_report(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")
        print(f"provider_discovery_report={path}")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only provider target discovery")
    parser.add_argument("--provider", choices=("dart",), default="dart")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output")
    parser.add_argument("--today", help="Override discovery end date (YYYY-MM-DD or YYYYMMDD)")
    parser.add_argument("--max-targets", type=int, default=2)
    parser.add_argument("--page-count", type=int, default=100)
    args = parser.parse_args(argv)

    if args.max_targets < 1:
        raise SystemExit("--max-targets must be >= 1")
    if args.page_count < 1 or args.page_count > 100:
        raise SystemExit("--page-count must be between 1 and 100")

    load_env_file(Path(args.env_file))
    today = parse_compact_or_iso_date(args.today) if args.today else None
    try:
        payload = discover_dart_targets(
            client=DartClient.from_env(),
            today=today,
            max_targets=args.max_targets,
            page_count=args.page_count,
        )
    except (ExternalProviderError, OSError, ValueError) as exc:
        payload = {
            "provider": "DART",
            "status_code": "BLOCKED_WITH_REDACTED_REASON",
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "reason_message": redact_secret_text(str(exc)),
        }
        write_report(payload, args.output)
        return 2
    write_report(payload, args.output)
    return 0 if payload["status_code"] == "DONE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
