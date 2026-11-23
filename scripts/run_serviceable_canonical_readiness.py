#!/usr/bin/env python3
"""Run the canonical serviceable top-200/30-day readiness artifact gate.

Stage order:
1. evidence-contract
2. source-governance
3. batch-artifact
4. readiness-capture
5. autoresearch-validator
6. verification-doc

The pipeline is fail-closed: it records redacted stage evidence and writes the
validator ``result.json`` even when live provider, PostgreSQL, Redis, or auth
preconditions are unavailable. It never fabricates provider rows or edits result
JSON by hand after the validator runs.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import load_env_file  # noqa: E402
from apps.api.harness.core.logging import redact_secret_text  # noqa: E402

DEFAULT_REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"
DEFAULT_SPEC_DIR = PROJECT_ROOT / ".omx" / "specs" / "autoresearch-service-readiness-top200-30d"
DEFAULT_RESULT_PATH = DEFAULT_SPEC_DIR / "result.json"
DEFAULT_SOURCE_LATEST = DEFAULT_REPORT_DIR / "krx-source-governance-latest.json"
DEFAULT_BATCH_LATEST = DEFAULT_REPORT_DIR / "serviceable-top200-30d-latest.json"
DEFAULT_READINESS_LATEST = DEFAULT_REPORT_DIR / "data-readiness-latest.json"
SERVICEABLE_BATCH_ARTIFACT_SQL = """
/* sql_id: capture_serviceable_top200_30d_batch_artifact */
SELECT
  selected_count,
  expected_member_days,
  observed_member_days,
  missing_member_days,
  coverage_ratio
FROM serviceable_top200_30d_coverage_view;
"""
REQUIRED_ENV_OVERRIDES = {
    "HARNESS_BATCH_KRX_ENABLED": "true",
    "HARNESS_BATCH_KRX_SOURCE": "KRX",
    "HARNESS_BATCH_KRX_POLICY": "OFFICIAL_KRX_APPROVED",
    "HARNESS_BATCH_KRX_UNIVERSE_CODE": "DOMESTIC_TOP200_MARKET_CAP",
    "HARNESS_BATCH_KRX_UNIVERSE_SIZE": "200",
    "HARNESS_BATCH_KRX_UNIVERSE_MARKETS": "KOSPI,KOSDAQ",
    "HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO": "1.0",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp_slug(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    os.replace(temporary, path)


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in {None, ""}:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def build_batch_artifact(
    *,
    metrics: dict[str, Any],
    redis_evidence: dict[str, Any],
    batch_run_report: str | None,
    min_selected: int,
    required_coverage_ratio: Decimal,
    generated_at: str,
) -> dict[str, Any]:
    """Build the canonical serviceable batch artifact from collected metrics.

    This helper is used by tests and by operator tooling as a pure contract
    function; provider rows are read elsewhere and are never fabricated here.
    """

    selected_count = int_value(metrics.get("selected_count"))
    target_size = int_value(metrics.get("target_size")) or min_selected
    expected_member_days = int_value(metrics.get("expected_member_days"))
    observed_member_days = int_value(metrics.get("observed_member_days"))
    missing_member_days = int_value(metrics.get("missing_member_days"))
    coverage_ratio = decimal_value(metrics.get("coverage_ratio"))
    synthetic_krx_price_rows = int_value(metrics.get("synthetic_krx_price_rows"))
    redis_ready = (
        redis_evidence.get("ping") is True
        and redis_evidence.get("lock_acquired") is True
        and redis_evidence.get("lock_released") is True
    )
    redis = dict(redis_evidence)
    redis["status_code"] = "READY" if redis_ready else "BLOCKED"
    blocking_reasons: list[str] = []
    if selected_count < min_selected:
        blocking_reasons.append(
            f"Selected universe count {selected_count} is below required {min_selected}."
        )
    if expected_member_days <= 0:
        blocking_reasons.append("No official KRX expected member-day denominator is persisted.")
    if missing_member_days > 0:
        blocking_reasons.append(f"{missing_member_days} expected member-days are missing bars.")
    if coverage_ratio < required_coverage_ratio:
        blocking_reasons.append(
            f"Coverage ratio {coverage_ratio} is below required {required_coverage_ratio}."
        )
    if synthetic_krx_price_rows > 0:
        blocking_reasons.append(
            f"KRX provider rows include synthetic rows: {synthetic_krx_price_rows}."
        )
    if not redis_ready:
        blocking_reasons.append("Redis ping/lock readiness is required.")
    provider_blockers = {
        "krx_provider_done": "KRX provider lineage evidence is missing.",
        "official_krx_policy_rows": "Official KRX policy lineage evidence is missing.",
        "official_krx_price_rows": "Official KRX price rows are missing.",
        "official_krx_trading_days": "Official KRX trading-day coverage is missing.",
        "ecos_provider_done": "ECOS lineage evidence is missing.",
        "opendart_provider_done": "OpenDART lineage evidence is missing.",
        "ecos_parseable_rows": "Parseable ECOS rows are missing.",
        "opendart_document_sources": "OpenDART document source rows are missing.",
        "opendart_document_chunks": "OpenDART document chunks are missing.",
    }
    for key, message in provider_blockers.items():
        if int_value(metrics.get(key)) <= 0:
            blocking_reasons.append(message)
    ready = not blocking_reasons
    top200 = {
        "snapshot_id": metrics.get("snapshot_id"),
        "universe_code": metrics.get("universe_code") or "DOMESTIC_TOP200_MARKET_CAP",
        "source_code": "KRX",
        "source_policy_code": "OFFICIAL_KRX_APPROVED",
        "selected_count": selected_count,
        "target_size": target_size,
        "required_count": min_selected,
        "expected_member_days": expected_member_days,
        "observed_member_days": observed_member_days,
        "missing_member_days": missing_member_days,
        "expected_trading_days": int_value(metrics.get("expected_trading_days")),
        "covered_tickers": int_value(metrics.get("covered_tickers")),
        "coverage_ratio": float(coverage_ratio),
        "status_code": "READY" if not blocking_reasons[:5] else "BLOCKED",
        "blocking_reasons": blocking_reasons,
    }
    return {
        "schema_version": "1.0",
        "artifact_kind": "serviceable_top200_30d_batch",
        "captured_at": generated_at,
        "captured_by": "scripts/run_serviceable_canonical_readiness.py",
        "source_code": "KRX",
        "source_policy_code": "OFFICIAL_KRX_APPROVED",
        "top200_coverage": top200,
        "serviceable_top200_30d": top200,
        "redis": redis,
        "redis_ping": redis_ready,
        "provider_summary": {"is_synthetic": synthetic_krx_price_rows > 0},
        "synthetic_provider_row_count": synthetic_krx_price_rows,
        "no_fabricated_provider_rows": synthetic_krx_price_rows == 0,
        "batch_run_report": batch_run_report,
        "sql_ids": ["capture_serviceable_top200_30d_batch_artifact"],
        "status_code": "READY" if ready else "BLOCKED",
        "passed": ready,
        "errors": blocking_reasons,
    }


def write_batch_artifact(
    *,
    artifact: dict[str, Any],
    output_dir: Path,
    latest_name: str,
    min_selected: int,
    required_coverage_ratio: Decimal,
) -> tuple[Path, Path, bool]:
    """Write timestamped and latest batch artifacts.

    ``latest`` is refreshed for BLOCKED outcomes too, preventing stale green
    serviceability evidence from being reused after a failed live capture.
    """

    _ = (min_selected, required_coverage_ratio)
    slug = timestamp_slug(utc_now())
    artifact_path = output_dir / f"serviceable-top200-30d-{slug}.json"
    latest_path = output_dir / latest_name
    atomic_write_json(artifact_path, artifact)
    atomic_write_json(latest_path, artifact | {"canonical_latest_source": str(artifact_path)})
    return artifact_path, latest_path, True


def redacted_command(command: list[str]) -> str:
    return redact_secret_text(" ".join(shlex.quote(part) for part in command))


def run_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "command": redacted_command(command),
        "returncode": completed.returncode,
        "stdout": redact_secret_text(completed.stdout[-8000:]),
        "stderr": redact_secret_text(completed.stderr[-8000:]),
        "ok": completed.returncode == 0,
    }


def base_env(args: argparse.Namespace) -> dict[str, str]:
    load_env_file(args.env_file)
    env = dict(os.environ)
    env.update(REQUIRED_ENV_OVERRIDES)
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    return env


def evidence_contract_stage(args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    help_result = run_command(
        [
            args.python_bin,
            "scripts/verify_serviceable_readiness.py",
            "--help",
        ],
        env=env,
        timeout_seconds=30,
    )
    required_fragments = [
        "--source-governance-report",
        "--batch-report",
        "--readiness-url",
        "--readiness-report",
        "--require-official-krx",
        "--require-opendart-lineage",
        "--require-ecos-lineage",
        "--require-docs-sync",
        "--no-fabricated-provider-rows",
        "--result-json",
    ]
    mission_path = DEFAULT_SPEC_DIR / "mission.md"
    sandbox_path = DEFAULT_SPEC_DIR / "sandbox.md"
    mission_text = mission_path.read_text(encoding="utf-8") if mission_path.exists() else ""
    sandbox_text = sandbox_path.read_text(encoding="utf-8") if sandbox_path.exists() else ""
    errors = [
        fragment for fragment in required_fragments if fragment not in help_result["stdout"]
    ]
    if "scripts/verify_serviceable_readiness.py" not in mission_text:
        errors.append("mission.md lacks validator command")
    if "--no-fabricated-provider-rows" not in sandbox_text:
        errors.append("sandbox.md lacks no-fabricated-provider-rows flag")
    return {
        "stage": "evidence-contract",
        "ok": help_result["ok"] and not errors,
        "errors": errors,
        "validator_help": help_result,
        "mission_path": str(mission_path),
        "sandbox_path": str(sandbox_path),
    }


def source_governance_stage(
    args: argparse.Namespace,
    env: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    output = args.report_dir / f"krx-source-governance-{timestamp_slug(now)}.json"
    result = run_command(
        [
            args.python_bin,
            "scripts/capture_krx_source_governance.py",
            "--env-file",
            str(args.env_file),
            "--output",
            str(output),
            "--latest",
            str(args.source_governance_latest),
        ],
        env=env,
        timeout_seconds=args.provider_timeout_seconds,
    )
    return {
        "stage": "source-governance",
        "ok": result["ok"],
        "artifact_path": str(output),
        "latest_path": str(args.source_governance_latest),
        "command_result": result,
    }


def batch_artifact_stage(
    args: argparse.Namespace,
    env: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    raw_batch_report = PROJECT_ROOT / ".omx" / "reports" / "batch" / (
        f"serviceable-top200-30d-run-{timestamp_slug(now)}.json"
    )
    command_results: list[dict[str, Any]] = []
    if not args.skip_batch_run:
        command_results.append(
            run_command(
                [
                    "scripts/run_batch_pipeline.sh",
                    "--profile",
                    "full-mvp",
                    "--stages",
                    "provider",
                    "--provider-strictness",
                    "required",
                    "--lookback-days",
                    "30",
                    "--env-file",
                    str(args.env_file),
                    "--report",
                    str(raw_batch_report),
                ],
                env=env,
                timeout_seconds=args.batch_timeout_seconds,
            )
        )
    output = args.report_dir / f"serviceable-top200-30d-{timestamp_slug(now)}.json"
    command_results.append(
        run_command(
            [
                args.python_bin,
                "scripts/capture_serviceable_top200_30d_artifact.py",
                "--env-file",
                str(args.env_file),
                "--output",
                str(output),
                "--latest",
                str(args.batch_latest),
            ],
            env=env,
            timeout_seconds=args.db_timeout_seconds,
        )
    )
    return {
        "stage": "batch-artifact",
        "ok": all(item["ok"] for item in command_results),
        "artifact_path": str(output),
        "latest_path": str(args.batch_latest),
        "raw_batch_report": str(raw_batch_report),
        "command_results": command_results,
    }


def fetch_readiness_url(
    args: argparse.Namespace,
    env: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if args.readiness_bearer_token_env:
        token = env.get(args.readiness_bearer_token_env, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(args.readiness_url, headers=headers)
    output = args.report_dir / f"data-readiness-{timestamp_slug(now)}.json"
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - operator URL
            payload = json.loads(response.read().decode("utf-8"))
        atomic_write_json(output, payload)
        atomic_write_json(args.readiness_latest, payload | {"canonical_latest_source": str(output)})
        return {"ok": True, "artifact_path": str(output), "latest_path": str(args.readiness_latest)}
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "artifact_path": str(output),
            "latest_path": str(args.readiness_latest),
            "error": redact_secret_text(str(exc)),
        }


def readiness_capture_stage(
    args: argparse.Namespace,
    env: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    if args.readiness_url:
        result = fetch_readiness_url(args, env, now)
        return {"stage": "readiness-capture", **result}
    output = args.report_dir / f"data-readiness-{timestamp_slug(now)}.json"
    result = run_command(
        [
            args.python_bin,
            "scripts/capture_data_readiness.py",
            "--env-file",
            str(args.env_file),
            "--output",
            str(output),
            "--latest",
            str(args.readiness_latest),
        ],
        env=env,
        timeout_seconds=args.db_timeout_seconds,
    )
    return {
        "stage": "readiness-capture",
        "ok": result["ok"],
        "artifact_path": str(output),
        "latest_path": str(args.readiness_latest),
        "command_result": result,
    }


def validator_stage(args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    command = [
        args.python_bin,
        "scripts/verify_serviceable_readiness.py",
        "--source-governance-report",
        str(args.source_governance_latest),
        "--batch-report",
        str(args.batch_latest),
        "--universe-code",
        "DOMESTIC_TOP200_MARKET_CAP",
        "--min-selected",
        "200",
        "--required-coverage-ratio",
        "1.0",
        "--require-official-krx",
        "--require-opendart-lineage",
        "--require-ecos-lineage",
        "--require-docs-sync",
        "--no-fabricated-provider-rows",
        "--result-json",
        str(args.result_json),
    ]
    if args.readiness_url:
        command.extend(["--readiness-url", args.readiness_url])
        if args.readiness_bearer_token_env:
            command.extend(["--readiness-bearer-token-env", args.readiness_bearer_token_env])
    else:
        command.extend(["--readiness-report", str(args.readiness_latest)])
    result = run_command(command, env=env, timeout_seconds=args.validator_timeout_seconds)
    return {
        "stage": "autoresearch-validator",
        "ok": result["ok"],
        "result_json": str(args.result_json),
        "command_result": result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--source-governance-latest", type=Path, default=DEFAULT_SOURCE_LATEST)
    parser.add_argument("--batch-latest", type=Path, default=DEFAULT_BATCH_LATEST)
    parser.add_argument("--readiness-latest", type=Path, default=DEFAULT_READINESS_LATEST)
    parser.add_argument("--result-json", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("--readiness-url")
    parser.add_argument("--readiness-bearer-token-env")
    parser.add_argument("--skip-batch-run", action="store_true")
    parser.add_argument("--provider-timeout-seconds", type=int, default=120)
    parser.add_argument("--batch-timeout-seconds", type=int, default=1800)
    parser.add_argument("--db-timeout-seconds", type=int, default=120)
    parser.add_argument("--validator-timeout-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    env = base_env(args)
    stages = [
        evidence_contract_stage(args, env),
        source_governance_stage(args, env, now),
        batch_artifact_stage(args, env, now),
        readiness_capture_stage(args, env, now),
        validator_stage(args, env),
    ]
    ok = all(stage.get("ok") for stage in stages)
    report = {
        "schema_version": "1.0",
        "artifact_kind": "serviceable_canonical_readiness_run",
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "finished_at": utc_now().isoformat().replace("+00:00", "Z"),
        "ok": ok,
        "stage_order": [stage["stage"] for stage in stages],
        "stages": stages,
        "result_json": str(args.result_json),
        "no_mock_policy": (
            "No provider rows are generated by this wrapper; provider evidence is live-only."
        ),
    }
    report_path = args.report_dir / f"serviceable-canonical-run-{timestamp_slug(now)}.json"
    latest_report_path = args.report_dir / "serviceable-canonical-run-latest.json"
    atomic_write_json(report_path, report)
    atomic_write_json(latest_report_path, report | {"canonical_latest_source": str(report_path)})
    print(json.dumps({"ok": ok, "report": str(report_path), "result_json": str(args.result_json)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
