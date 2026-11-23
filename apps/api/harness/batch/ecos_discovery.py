"""Read-only ECOS target discovery and parseable-row gate.

The command in this module performs only official ECOS GET requests. It emits a
secret-free target catalog that can be copied into
``HARNESS_BATCH_ECOS_TARGETS_JSON`` and fails closed unless at least one selected
target returns rows that the production ECOS parser can persist.
"""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.batch.providers import (
    EcosIndicatorTarget,
    ecos_target_ref,
    parse_ecos_macro_payload,
)
from apps.api.harness.core.config import load_env_file
from apps.api.harness.core.logging import redact_secret_text
from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.external.public_data import EcosClient


@dataclass(frozen=True)
class EcosDiscoveryCandidate:
    """One official ECOS statistic/item pair to verify through metadata + rows."""

    statistic_code: str
    item_code: str
    indicator_name: str
    cycle: str = "D"
    unit_fallback: str = ""


DEFAULT_ECOS_CANDIDATES: tuple[EcosDiscoveryCandidate, ...] = (
    EcosDiscoveryCandidate(
        statistic_code="722Y001",
        item_code="0101000",
        indicator_name="base_rate",
        unit_fallback="연%",
    ),
    EcosDiscoveryCandidate(
        statistic_code="731Y001",
        item_code="0000001",
        indicator_name="usd_krw_reference_rate",
        unit_fallback="원",
    ),
    EcosDiscoveryCandidate(
        statistic_code="817Y002",
        item_code="010101000",
        indicator_name="call_rate_overnight_all",
        unit_fallback="연%",
    ),
    EcosDiscoveryCandidate(
        statistic_code="802Y001",
        item_code="0001000",
        indicator_name="kospi_index",
        unit_fallback="1980.01.04=100",
    ),
    EcosDiscoveryCandidate(
        statistic_code="521Y001",
        item_code="A001",
        indicator_name="news_sentiment_index",
    ),
)


def _official_rows(payload: dict[str, Any], root_key: str) -> list[dict[str, Any]]:
    """Extract official ECOS ``row`` entries from one metadata/search payload."""

    root = payload.get(root_key)
    rows = root.get("row") if isinstance(root, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
        return rows
    return []


def _official_total_count(payload: dict[str, Any], root_key: str) -> int:
    root = payload.get(root_key)
    if not isinstance(root, dict):
        return 0
    raw_count = root.get("list_total_count") or 0
    try:
        return int(raw_count)
    except (TypeError, ValueError):
        return 0


def _metadata_for_candidate(
    *,
    table_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    candidate: EcosDiscoveryCandidate,
) -> dict[str, Any] | None:
    table = next(
        (
            row
            for row in table_rows
            if str(row.get("STAT_CODE") or "").strip() == candidate.statistic_code
        ),
        None,
    )
    item = next(
        (
            row
            for row in item_rows
            if str(row.get("ITEM_CODE") or "").strip() == candidate.item_code
            and str(row.get("CYCLE") or "").strip() == candidate.cycle
        ),
        None,
    )
    if table is None or item is None:
        return None
    return {
        "statistic_code": candidate.statistic_code,
        "statistic_name": str(table.get("STAT_NAME") or item.get("STAT_NAME") or "").strip(),
        "cycle": candidate.cycle,
        "searchable": str(table.get("SRCH_YN") or "").strip(),
        "item_code": candidate.item_code,
        "item_name": str(item.get("ITEM_NAME") or "").strip(),
        "unit": str(item.get("UNIT_NAME") or candidate.unit_fallback or "").strip(),
        "metadata_start_time": str(item.get("START_TIME") or "").strip(),
        "metadata_end_time": str(item.get("END_TIME") or "").strip(),
        "metadata_data_count": item.get("DATA_CNT"),
    }


def _target_from_metadata(
    *,
    metadata: dict[str, Any],
    candidate: EcosDiscoveryCandidate,
    start: str,
    end: str,
    lookback_days: int,
    date_lag_days: int,
) -> EcosIndicatorTarget:
    return EcosIndicatorTarget(
        statistic_code=candidate.statistic_code,
        cycle=candidate.cycle,
        start=start,
        end=end,
        indicator_name=candidate.indicator_name,
        unit=str(metadata.get("unit") or candidate.unit_fallback or ""),
        item_codes=(candidate.item_code,),
        date_lag_days=date_lag_days,
        lookback_days=lookback_days,
    )


def _target_json(target: EcosIndicatorTarget) -> dict[str, Any]:
    return {
        "statistic_code": target.statistic_code,
        "cycle": target.cycle,
        "indicator_name": target.indicator_name,
        "unit": target.unit,
        "item_codes": list(target.item_codes),
        "lookback_days": target.lookback_days,
        "date_lag_days": target.date_lag_days,
    }


def discover_ecos_targets(
    *,
    client: EcosClient,
    today: date | None = None,
    lookback_days: int = 14,
    date_lag_days: int = 1,
    max_targets: int = 2,
    min_parseable_targets: int = 1,
    candidates: tuple[EcosDiscoveryCandidate, ...] = DEFAULT_ECOS_CANDIDATES,
) -> dict[str, Any]:
    """Discover official ECOS targets and assert parser-ready live rows."""

    base_date = today or date.today()
    resolved_end = base_date - timedelta(days=date_lag_days)
    resolved_start = resolved_end - timedelta(days=lookback_days)
    start = resolved_start.strftime("%Y%m%d")
    end = resolved_end.strftime("%Y%m%d")

    key_payload = client.key_statistic_list(end_row=100)
    table_payload = client.statistic_table_list(end_row=1000)
    table_rows = _official_rows(table_payload, "StatisticTableList")
    searchable_daily_tables = [
        {
            "statistic_code": str(row.get("STAT_CODE") or "").strip(),
            "statistic_name": str(row.get("STAT_NAME") or "").strip(),
            "cycle": str(row.get("CYCLE") or "").strip(),
            "searchable": str(row.get("SRCH_YN") or "").strip(),
        }
        for row in table_rows
        if str(row.get("SRCH_YN") or "").strip() == "Y"
        and "D" in str(row.get("CYCLE") or "")
    ]

    candidate_reports: list[dict[str, Any]] = []
    selected_targets: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            item_payload = client.statistic_item_list(
                statistic_code=candidate.statistic_code,
                end_row=1000,
            )
            item_rows = _official_rows(item_payload, "StatisticItemList")
            metadata = _metadata_for_candidate(
                table_rows=table_rows,
                item_rows=item_rows,
                candidate=candidate,
            )
            if metadata is None:
                candidate_reports.append(
                    {
                        "candidate": candidate.__dict__,
                        "status": "METADATA_MISSING",
                        "parseable_row_count": 0,
                    }
                )
                continue
            target = _target_from_metadata(
                metadata=metadata,
                candidate=candidate,
                start=start,
                end=end,
                lookback_days=lookback_days,
                date_lag_days=date_lag_days,
            )
            payload = client.statistic_search(
                statistic_code=target.statistic_code,
                cycle=target.cycle,
                start=target.start,
                end=target.end,
                item_codes=target.item_codes,
            )
            parsed_rows = parse_ecos_macro_payload(payload=payload, target=target)
            report = {
                "candidate": candidate.__dict__,
                "status": "PARSEABLE_ROWS" if parsed_rows else "NO_DATA",
                "target_ref": ecos_target_ref(target),
                "generated_target_json": _target_json(target),
                "official_metadata": metadata,
                "parseable_row_count": len(parsed_rows),
                "latest_reference_date": (
                    max(row["reference_date"] for row in parsed_rows).isoformat()
                    if parsed_rows
                    else None
                ),
            }
            candidate_reports.append(report)
            if parsed_rows and len(selected_targets) < max_targets:
                selected_targets.append(report)
        except Exception as exc:  # noqa: BLE001 - discovery report must keep scanning candidates
            candidate_reports.append(
                {
                    "candidate": candidate.__dict__,
                    "status": "FAILED",
                    "parseable_row_count": 0,
                    "reason": redact_secret_text(str(exc)),
                }
            )

    gate_ok = len(selected_targets) >= min_parseable_targets
    return {
        "schema_version": "1.0",
        "provider_code": "ECOS",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": {
            "start": start,
            "end": end,
            "lookback_days": lookback_days,
            "date_lag_days": date_lag_days,
        },
        "official_endpoint_evidence": {
            "key_statistic_list_rows": _official_total_count(key_payload, "KeyStatisticList"),
            "statistic_table_list_rows": _official_total_count(
                table_payload, "StatisticTableList"
            ),
            "searchable_daily_table_count": len(searchable_daily_tables),
            "searchable_daily_tables": searchable_daily_tables,
        },
        "gate": {
            "status": "PASS" if gate_ok else "FAIL",
            "min_parseable_targets": min_parseable_targets,
            "parseable_targets": len(selected_targets),
        },
        "selected_targets": selected_targets,
        "candidate_reports": candidate_reports,
        "harness_batch_ecos_targets_json": [
            target["generated_target_json"] for target in selected_targets
        ],
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover live parseable ECOS batch targets.")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lookback-days", type=_positive_int, default=14)
    parser.add_argument("--date-lag-days", type=int, default=1)
    parser.add_argument("--max-targets", type=_positive_int, default=2)
    parser.add_argument("--min-parseable-targets", type=_positive_int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.date_lag_days < 0:
        raise SystemExit("--date-lag-days must be >= 0")
    load_env_file(args.env_file)
    try:
        report = discover_ecos_targets(
            client=EcosClient.from_env(),
            lookback_days=args.lookback_days,
            date_lag_days=args.date_lag_days,
            max_targets=args.max_targets,
            min_parseable_targets=args.min_parseable_targets,
        )
    except ExternalProviderError as exc:
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "provider_code": "ECOS",
                    "gate": {"status": "FAIL"},
                    "reason": redact_secret_text(str(exc)),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(report, ensure_ascii=False, default=str))
    raise SystemExit(0 if report["gate"]["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
