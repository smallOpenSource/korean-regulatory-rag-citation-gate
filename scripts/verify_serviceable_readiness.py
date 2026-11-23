#!/usr/bin/env python3
"""Validate serviceable top-200/30-day readiness evidence.

The validator is intentionally read-only: it checks secret-free source-governance,
batch, and readiness artifacts and writes the embedded autoresearch result
contract. It never contacts providers or mutates PostgreSQL/Redis.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.logging import redact_secret_text  # noqa: E402

DEFAULT_RESULT_PATH = (
    PROJECT_ROOT
    / ".omx"
    / "specs"
    / "autoresearch-service-readiness-top200-30d"
    / "result.json"
)
DEFAULT_DOC_SYNC_PATHS = (
    "docs/batch/BATCH-01_pipeline_overview.md",
    "docs/batch/BATCH-03_structured_collect.md",
    "docs/api/API-01_contracts.yaml",
    "docs/config/CFG-01_env_and_config.md",
    "docs/runbooks/OPS-03_troubleshooting.md",
    "docs/test/TEST-01_test_strategy.md",
)
COVERAGE_SQL = """
/* sql_id: verify_serviceable_top200_30d_coverage */
WITH latest_snapshot AS (
    SELECT id, selected_count
    FROM market_universe_snapshots
    WHERE universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
      AND source_code = 'KRX'
      AND source_policy_code = 'OFFICIAL_KRX_APPROVED'
    ORDER BY as_of_date DESC, resolved_trading_date DESC, created_at DESC
    LIMIT 1
), coverage AS (
    SELECT count(*) FILTER (WHERE is_expected_trading_day IS TRUE)::integer
               AS expected_member_days,
           count(*) FILTER (
               WHERE is_expected_trading_day IS TRUE AND has_valid_bar IS TRUE
           )::integer AS observed_member_days,
           count(*) FILTER (
               WHERE is_expected_trading_day IS TRUE AND has_valid_bar IS FALSE
           )::integer AS missing_member_days
    FROM market_universe_coverage_daily daily
    JOIN latest_snapshot ON latest_snapshot.id = daily.snapshot_id
)
SELECT latest_snapshot.selected_count,
       COALESCE(coverage.expected_member_days, 0) AS expected_member_days,
       COALESCE(coverage.observed_member_days, 0) AS observed_member_days,
       COALESCE(coverage.missing_member_days, 0) AS missing_member_days,
       CASE
           WHEN COALESCE(coverage.expected_member_days, 0) = 0 THEN 0::numeric
           ELSE COALESCE(coverage.observed_member_days, 0)::numeric
                / coverage.expected_member_days::numeric
       END AS coverage_ratio
FROM latest_snapshot
LEFT JOIN coverage ON TRUE;
"""
SECRET_ENV_PARTS = (
    "SECRET",
    "TOKEN",
    "API_KEY",
    "APIKEY",
    "AUTH_KEY",
    "SERVICE_KEY",
    "APP_SECRET",
    "PASSWORD",
)
LINEAGE_CHECK_ALIASES = {
    "opendart": {"provider.opendart_30d_lineage", "provider.dart_parseable_documents"},
    "ecos": {"provider.ecos_macro_window", "provider.ecos_parseable_rows"},
}


class ValidationError(RuntimeError):
    """Raised for evidence contract failures."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"missing artifact: {path}")
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"artifact must be a JSON object: {path}")
    return value


def decimal_value(value: Any, *, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def iter_nodes(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, Mapping):
        for item in value.values():
            yield from iter_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_nodes(item)


def iter_mapping_nodes(value: Any) -> Iterable[Mapping[str, Any]]:
    for node in iter_nodes(value):
        if isinstance(node, Mapping):
            yield node


def find_first_mapping_with_key(value: Any, key: str) -> Mapping[str, Any] | None:
    for node in iter_mapping_nodes(value):
        nested = node.get(key)
        if isinstance(nested, Mapping):
            return nested
    return None


def find_top200_coverage(value: Any) -> Mapping[str, Any] | None:
    direct_paths = (
        ("domestic_market", "top200_coverage"),
        ("postconditions", "domestic_market", "top200_coverage"),
        ("postconditions", "top200_coverage"),
        ("serviceable_top200_30d", "top200_coverage"),
        ("serviceable_top200_30d",),
        ("top200_coverage",),
    )
    for path in direct_paths:
        current: Any = value
        for segment in path:
            if not isinstance(current, Mapping):
                current = None
                break
            current = current.get(segment)
        if isinstance(current, Mapping) and (
            "selected_count" in current or "coverage_ratio" in current
        ):
            return current
    return find_first_mapping_with_key(value, "top200_coverage")


def collect_checks(readiness: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    checks: dict[str, Mapping[str, Any]] = {}
    for node in iter_mapping_nodes(readiness):
        code = node.get("check_code")
        if isinstance(code, str):
            checks.setdefault(code, node)
    return checks


def sensitive_env_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        if any(part in key.upper() for part in SECRET_ENV_PARTS):
            normalized = value.strip()
            if normalized and normalized.lower() not in {"changeme", "placeholder", "example"}:
                values.append(normalized)
    return values


def assert_no_secret_values(*artifacts: Mapping[str, Any]) -> None:
    text = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in artifacts)
    leaked = [secret for secret in sensitive_env_values() if secret in text]
    if leaked:
        raise ValidationError(f"secret value leaked in artifacts: {len(leaked)} value(s)")


def has_forbidden_provider_header(value: Any) -> bool:
    for node in iter_mapping_nodes(value):
        for key, item in node.items():
            key_l = str(key).lower()
            if (
                "header" in key_l
                and isinstance(item, Mapping)
                and any(str(header).lower() == "auth_key" for header in item)
            ):
                return True
            if key_l in {"auth_key", "authorization"} and item not in {"<redacted>", None, ""}:
                return True
    return False


def validate_source_governance(
    report: Mapping[str, Any],
    *,
    require_official_krx: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    authorization_status = str(report.get("authorization_status") or "").upper()
    source_policy_code = str(report.get("source_policy_code") or "").upper()
    endpoints = as_list(report.get("endpoints"))

    if authorization_status != "APPROVED":
        errors.append("source governance authorization_status must be APPROVED")
    if require_official_krx and source_policy_code != "OFFICIAL_KRX_APPROVED":
        errors.append("source governance source_policy_code must be OFFICIAL_KRX_APPROVED")
    if report.get("secret_redacted") is not True:
        errors.append("source governance report must set secret_redacted=true")
    if not endpoints:
        errors.append("source governance report must include endpoint probe evidence")
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, Mapping):
            errors.append(f"endpoint[{index}] must be an object")
            continue
        if int_value(endpoint.get("http_status")) not in {200, 204}:
            errors.append(f"endpoint[{index}] must have successful http_status")
        if int_value(endpoint.get("returned_row_count")) < 0:
            errors.append(f"endpoint[{index}] returned_row_count must be non-negative")
        if not endpoint.get("evidence_hash") and not endpoint.get("redacted_evidence_hash"):
            errors.append(f"endpoint[{index}] must include redacted evidence hash")
    if has_forbidden_provider_header(report):
        errors.append("source governance report must not persist AUTH_KEY/full request headers")

    return {
        "authorization_status": authorization_status or None,
        "source_policy_code": source_policy_code or None,
        "endpoint_count": len(endpoints),
        "errors": errors,
    }


def redis_status_from_batch(report: Mapping[str, Any]) -> bool:
    if report.get("redis_ping") is True:
        return True
    redis = report.get("redis")
    if isinstance(redis, Mapping) and (
        redis.get("ping") is True or redis.get("status_code") == "READY"
    ):
        return True
    for node in iter_mapping_nodes(report):
        if (
            str(node.get("check_code") or "").lower() in {"redis.lock", "redis.ping"}
            and (node.get("status_code") in {"READY", "DONE"} or node.get("ok") is True)
        ):
            return True
    return False


def validate_top200_coverage(
    payload: Mapping[str, Any],
    *,
    universe_code: str,
    min_selected: int,
    required_coverage_ratio: Decimal,
) -> dict[str, Any]:
    selected_count = int_value(payload.get("selected_count"))
    expected_member_days = int_value(payload.get("expected_member_days"))
    observed_member_days = int_value(
        payload.get("observed_member_days") or payload.get("valid_member_days")
    )
    missing_member_days = int_value(payload.get("missing_member_days"))
    if expected_member_days and "missing_member_days" not in payload:
        missing_member_days = max(expected_member_days - observed_member_days, 0)
    coverage_ratio = decimal_value(payload.get("coverage_ratio"))
    if expected_member_days > 0 and coverage_ratio == 0:
        coverage_ratio = Decimal(observed_member_days) / Decimal(expected_member_days)

    errors: list[str] = []
    if str(payload.get("universe_code") or universe_code) != universe_code:
        errors.append(f"top200 universe_code must be {universe_code}")
    if selected_count < min_selected:
        errors.append(f"selected_count {selected_count} is below {min_selected}")
    if expected_member_days <= 0:
        errors.append("expected_member_days must be positive")
    if missing_member_days != 0:
        errors.append(f"missing_member_days must be 0, got {missing_member_days}")
    if coverage_ratio < required_coverage_ratio:
        errors.append(f"coverage_ratio {coverage_ratio} is below {required_coverage_ratio}")
    if payload.get("status_code") and payload.get("status_code") != "READY":
        errors.append(f"top200 status_code must be READY, got {payload.get('status_code')}")

    return {
        "universe_code": str(payload.get("universe_code") or universe_code),
        "selected_count": selected_count,
        "expected_member_days": expected_member_days,
        "observed_member_days": observed_member_days,
        "missing_member_days": missing_member_days,
        "coverage_ratio": float(coverage_ratio),
        "status_code": payload.get("status_code"),
        "errors": errors,
    }


def validate_batch_report(
    report: Mapping[str, Any],
    *,
    universe_code: str,
    min_selected: int,
    required_coverage_ratio: Decimal,
    require_official_krx: bool,
    no_fabricated_provider_rows: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    if not redis_status_from_batch(report):
        errors.append("batch report must prove Redis ping or lock readiness")
    if require_official_krx:
        source_code = str(report.get("source_code") or "").upper()
        policy_code = str(report.get("source_policy_code") or "").upper()
        if source_code and source_code != "KRX":
            errors.append("batch report source_code must be KRX for official readiness")
        if policy_code and policy_code != "OFFICIAL_KRX_APPROVED":
            errors.append("batch report source_policy_code must be OFFICIAL_KRX_APPROVED")
    if no_fabricated_provider_rows:
        for node in iter_mapping_nodes(report):
            if node.get("is_synthetic") is True:
                errors.append("batch report contains is_synthetic=true provider evidence")
                break

    coverage = find_top200_coverage(report)
    coverage_result: dict[str, Any] | None = None
    if coverage is None:
        errors.append("batch report must include top200_coverage evidence")
    else:
        coverage_result = validate_top200_coverage(
            coverage,
            universe_code=universe_code,
            min_selected=min_selected,
            required_coverage_ratio=required_coverage_ratio,
        )
        errors.extend(f"batch {error}" for error in coverage_result["errors"])

    return {
        "redis_ready": redis_status_from_batch(report),
        "coverage": coverage_result,
        "errors": errors,
    }


def fetch_readiness(url: str, *, authorization: str | None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    if authorization:
        request.add_header("Authorization", authorization)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - local/operator URL
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValidationError(f"readiness URL returned HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise ValidationError(f"readiness URL unavailable: {redact_secret_text(str(exc))}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"readiness URL returned non-JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("readiness URL must return a JSON object")
    return payload


def validate_readiness_payload(
    readiness: Mapping[str, Any],
    *,
    universe_code: str,
    min_selected: int,
    required_coverage_ratio: Decimal,
    require_opendart_lineage: bool,
    require_ecos_lineage: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    domestic_market = readiness.get("domestic_market")
    if not isinstance(domestic_market, Mapping):
        raise ValidationError("readiness payload must include domestic_market object")
    coverage = domestic_market.get("top200_coverage")
    if not isinstance(coverage, Mapping):
        errors.append("readiness domestic_market.top200_coverage is missing")
        coverage_result = None
    else:
        coverage_result = validate_top200_coverage(
            coverage,
            universe_code=universe_code,
            min_selected=min_selected,
            required_coverage_ratio=required_coverage_ratio,
        )
        errors.extend(f"readiness {error}" for error in coverage_result["errors"])

    checks = collect_checks(readiness)
    for label, required, aliases in (
        ("OpenDART", require_opendart_lineage, LINEAGE_CHECK_ALIASES["opendart"]),
        ("ECOS", require_ecos_lineage, LINEAGE_CHECK_ALIASES["ecos"]),
    ):
        if not required:
            continue
        matched = [checks[code] for code in aliases if code in checks]
        if not matched:
            errors.append(f"readiness payload lacks {label} lineage check")
        elif all(check.get("status_code") != "READY" for check in matched):
            errors.append(f"readiness {label} lineage check is not READY")

    return {
        "status_code": readiness.get("status_code"),
        "domestic_market_status_code": domestic_market.get("status_code"),
        "coverage": coverage_result,
        "errors": errors,
    }


def validate_docs_sync(required_paths: list[str], *, universe_code: str) -> dict[str, Any]:
    errors: list[str] = []
    matched: list[str] = []
    for item in required_paths:
        path = PROJECT_ROOT / item
        if not path.exists():
            errors.append(f"missing docs sync path: {item}")
            continue
        text = path.read_text(errors="ignore")
        text_lower = text.lower()
        if (
            universe_code not in text
            and "top-200" not in text_lower
            and "top200" not in text_lower
        ):
            errors.append(f"docs path lacks serviceable top200 language: {item}")
        else:
            matched.append(item)
    return {"checked_paths": required_paths, "matched_paths": matched, "errors": errors}


def build_command() -> str:
    return redact_secret_text(" ".join(shlex.quote(part) for part in sys.argv))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-governance-report", type=Path, required=True)
    parser.add_argument("--batch-report", type=Path, required=True)
    parser.add_argument("--readiness-url")
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--readiness-authorization")
    parser.add_argument("--readiness-bearer-token-env")
    parser.add_argument("--universe-code", default="DOMESTIC_TOP200_MARKET_CAP")
    parser.add_argument("--min-selected", type=int, default=200)
    parser.add_argument("--required-coverage-ratio", default="1.0")
    parser.add_argument("--require-official-krx", action="store_true")
    parser.add_argument("--require-opendart-lineage", action="store_true")
    parser.add_argument("--require-ecos-lineage", action="store_true")
    parser.add_argument("--require-docs-sync", action="store_true")
    parser.add_argument("--docs-sync-path", action="append", default=[])
    parser.add_argument("--no-fabricated-provider-rows", action="store_true")
    parser.add_argument("--result-json", type=Path, default=DEFAULT_RESULT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    required_coverage_ratio = decimal_value(args.required_coverage_ratio, default=Decimal("1.0"))
    all_errors: list[str] = []
    result: dict[str, Any] = {
        "status": "failed",
        "passed": False,
        "checked_at": utc_now(),
        "validator_command": build_command(),
        "artifacts": {
            "source_governance_report": str(args.source_governance_report),
            "batch_report": str(args.batch_report),
            "readiness_url": args.readiness_url,
            "readiness_report": str(args.readiness_report) if args.readiness_report else None,
        },
        "universe_code": args.universe_code,
        "min_selected": args.min_selected,
        "required_coverage_ratio": float(required_coverage_ratio),
    }

    try:
        source_governance = load_json(args.source_governance_report)
        batch_report = load_json(args.batch_report)
        readiness_authorization = args.readiness_authorization
        if args.readiness_bearer_token_env:
            token = os.getenv(args.readiness_bearer_token_env, "").strip()
            if token:
                readiness_authorization = f"Bearer {token}"
        if args.readiness_report:
            readiness_payload = load_json(args.readiness_report)
        elif args.readiness_url:
            readiness_payload = fetch_readiness(
                args.readiness_url,
                authorization=readiness_authorization,
            )
        else:
            raise ValidationError("either --readiness-url or --readiness-report is required")

        assert_no_secret_values(source_governance, batch_report, readiness_payload)

        governance_result = validate_source_governance(
            source_governance,
            require_official_krx=args.require_official_krx,
        )
        batch_result = validate_batch_report(
            batch_report,
            universe_code=args.universe_code,
            min_selected=args.min_selected,
            required_coverage_ratio=required_coverage_ratio,
            require_official_krx=args.require_official_krx,
            no_fabricated_provider_rows=args.no_fabricated_provider_rows,
        )
        readiness_result = validate_readiness_payload(
            readiness_payload,
            universe_code=args.universe_code,
            min_selected=args.min_selected,
            required_coverage_ratio=required_coverage_ratio,
            require_opendart_lineage=args.require_opendart_lineage,
            require_ecos_lineage=args.require_ecos_lineage,
        )
        docs_result = None
        if args.require_docs_sync:
            docs_result = validate_docs_sync(
                args.docs_sync_path or list(DEFAULT_DOC_SYNC_PATHS),
                universe_code=args.universe_code,
            )
            all_errors.extend(docs_result["errors"])

        all_errors.extend(governance_result["errors"])
        all_errors.extend(batch_result["errors"])
        all_errors.extend(readiness_result["errors"])
        result.update(
            {
                "source_governance": governance_result,
                "batch": batch_result,
                "readiness": readiness_result,
                "docs_sync": docs_result,
                "coverage_ratio": (
                    readiness_result.get("coverage") or batch_result.get("coverage") or {}
                ).get("coverage_ratio", 0),
                "selected_count": (
                    readiness_result.get("coverage") or batch_result.get("coverage") or {}
                ).get("selected_count", 0),
                "errors": all_errors,
            }
        )
    except ValidationError as exc:
        all_errors.append(str(exc))
        result["errors"] = all_errors
    except Exception as exc:  # defensive: validator reports, never leaks raw provider stack details
        all_errors.append(redact_secret_text(str(exc)))
        result["errors"] = all_errors

    if not all_errors:
        result["status"] = "passed"
        result["passed"] = True
        result["verifier_signoff"] = "serviceable-readiness-validator"

    args.result_json.parent.mkdir(parents=True, exist_ok=True)
    args.result_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
