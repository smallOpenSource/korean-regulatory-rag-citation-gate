"""Serviceable top-200/30-day verification, docs, and report-redaction contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.harness.core.logging import redact_mapping, redact_secret_text
from apps.api.harness.core.sql import validate_sql_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICEABLE_DOC_PATHS = (
    PROJECT_ROOT / "docs" / "batch" / "BATCH-01_pipeline_overview.md",
    PROJECT_ROOT / "docs" / "batch" / "BATCH-03_structured_collect.md",
    PROJECT_ROOT / "docs" / "config" / "CFG-01_env_and_config.md",
    PROJECT_ROOT / "docs" / "runbooks" / "OPS-03_troubleshooting.md",
    PROJECT_ROOT / "docs" / "api" / "API-01_contracts.yaml",
    PROJECT_ROOT / "docs" / "test" / "TEST-01_test_strategy.md",
)
SERVICEABLE_PLAN_PATH = (
    PROJECT_ROOT / ".omx" / "plans" / "ralplan-live-canonical-serviceable-validator-artifacts.md"
)
COVERAGE_SQL_PROOF = """
/* sql_id: verify_serviceable_top200_30d_coverage */
SELECT
  selected_count,
  expected_member_days,
  observed_member_days,
  missing_member_days,
  coverage_ratio
FROM serviceable_top200_30d_coverage_view;
"""


def test_serviceable_coverage_sql_id_contract_is_locked() -> None:
    result = validate_sql_text(COVERAGE_SQL_PROOF, context="serviceable.coverage_sql_proof")

    assert result.ok, result.errors
    assert "verify_serviceable_top200_30d_coverage" in COVERAGE_SQL_PROOF


def test_serviceable_provider_lineage_query_prioritizes_required_non_krx_sources() -> None:
    spec = importlib.util.spec_from_file_location(
        "capture_serviceable_top200_30d_artifact",
        PROJECT_ROOT / "scripts" / "capture_serviceable_top200_30d_artifact.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = validate_sql_text(
        module.PROVIDER_LINEAGE_SQL,
        context="serviceable.provider_lineage_sql",
    )

    assert result.ok, result.errors
    assert "capture_serviceable_provider_lineage" in module.PROVIDER_LINEAGE_SQL
    assert "WHEN 'ECOS' THEN 1" in module.PROVIDER_LINEAGE_SQL
    assert "LIMIT 500" in module.PROVIDER_LINEAGE_SQL


def test_serviceable_docs_sync_mentions_top200_contract() -> None:
    missing = [
        str(path.relative_to(PROJECT_ROOT))
        for path in SERVICEABLE_DOC_PATHS
        if "DOMESTIC_TOP200_MARKET_CAP" not in path.read_text(encoding="utf-8")
    ]

    assert missing == []


def test_validator_command_and_completion_contract_are_documented() -> None:
    test_strategy = (PROJECT_ROOT / "docs" / "test" / "TEST-01_test_strategy.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (PROJECT_ROOT / "docs" / "runbooks" / "OPS-03_troubleshooting.md").read_text(
        encoding="utf-8"
    )
    sandbox = (
        PROJECT_ROOT / ".omx" / "specs" / "autoresearch-service-readiness-top200-30d" / "sandbox.md"
    ).read_text(encoding="utf-8")

    for text in (test_strategy, readme, runbook, sandbox):
        assert "scripts/verify_serviceable_readiness.py" in text
        assert "krx-source-governance" in text
        assert "serviceable-top200-30d" in text
        assert ".omx/specs/autoresearch-service-readiness-top200-30d/result.json" in text
        assert "--result-json" in text
        assert "--require-docs-sync" in text
        assert "--no-fabricated-provider-rows" in text

    for text in (test_strategy, readme, runbook):
        assert "coverage_ratio" in text
        assert "missing_member_days" in text


def test_serviceable_docs_use_supported_canonical_runner_flags() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in SERVICEABLE_DOC_PATHS)

    assert "scripts/run_serviceable_canonical_readiness.py --env-file .env" in docs
    assert "--skip-batch-run" in docs
    assert "--lookback-days 30 --capture-readiness-from-db" not in docs
    assert "--capture-readiness-from-db" not in docs


def test_serviceable_ralplan_and_batch_docs_keep_official_krx_policy_distinct() -> None:
    assert SERVICEABLE_PLAN_PATH.exists()
    ralplan = SERVICEABLE_PLAN_PATH.read_text(encoding="utf-8")
    structured_collect = (
        PROJECT_ROOT / "docs" / "batch" / "BATCH-03_structured_collect.md"
    ).read_text(encoding="utf-8")

    for stage in (
        "evidence-contract",
        "source-governance",
        "batch-artifact",
        "readiness-capture",
        "autoresearch-validator",
        "verification-doc",
    ):
        assert stage in ralplan
    assert "OFFICIAL_KRX_APPROVED" in structured_collect
    assert "PYKRX_AUXILIARY_APPROVED" in structured_collect
    assert "must not be promoted" in structured_collect
    assert "official top-200 readiness" in structured_collect


def test_report_redaction_covers_krx_auth_header_query_and_json_echoes() -> None:
    raw_text = (
        "AUTH_KEY=krx-secret "
        "?auth_key=query-secret&basDd=20260515 "
        "Authorization: Bearer bearer-secret"
    )
    redacted_text = redact_secret_text(raw_text)
    redacted_mapping = redact_mapping(
        {
            "AUTH_KEY": "header-secret",
            "KRX_API_KEY": "provider-secret",
            "nested": {"serviceKey": "data-go-secret"},
        }
    )

    for secret in ("krx-secret", "query-secret", "bearer-secret"):
        assert secret not in redacted_text
    assert "AUTH_KEY=<redacted>" in redacted_text
    assert "auth_key=<redacted>" in redacted_text.lower()
    assert "Bearer <redacted>" in redacted_text
    assert redacted_mapping == {
        "AUTH_KEY": "<redacted>",
        "KRX_API_KEY": "<redacted>",
        "nested": {"serviceKey": "<redacted>"},
    }


def test_validator_coverage_sql_is_sql_id_clean_when_validator_script_exposes_it() -> None:
    if importlib.util.find_spec("scripts.verify_serviceable_readiness") is None:
        pytest.skip("validator script is owned by backend validator lane")
    from scripts import verify_serviceable_readiness as verifier

    coverage_sql = getattr(verifier, "COVERAGE_SQL", None)
    if coverage_sql is None:
        pytest.skip("backend validator has not exposed COVERAGE_SQL yet")

    result = validate_sql_text(
        coverage_sql,
        context="verify_serviceable_readiness.COVERAGE_SQL",
    )

    assert result.ok, result.errors



def _load_script_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / relative_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_canonical_serviceable_artifact_scripts_are_documented_and_importable() -> None:
    script_paths = (
        "scripts/capture_krx_source_governance.py",
        "scripts/capture_serviceable_top200_30d_artifact.py",
        "scripts/capture_data_readiness.py",
        "scripts/run_serviceable_canonical_readiness.py",
    )
    for relative_path in script_paths:
        script = PROJECT_ROOT / relative_path
        assert script.exists()
        text = script.read_text(encoding="utf-8")
        assert "unittest.mock" not in text
        assert "canonical" in text.lower() or "readiness" in text.lower()
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "PYTHONPATH": f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}"},
        )
        assert result.returncode == 0, result.stderr


def test_source_governance_missing_live_gate_writes_failed_latest_without_secret(tmp_path) -> None:
    output = tmp_path / "krx-source-governance.json"
    latest = tmp_path / "krx-source-governance-latest.json"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HARNESS_BATCH_KRX_ENABLED=false\n"
        "HARNESS_BATCH_KRX_SOURCE=KRX\n"
        "HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED\n"
        "KRX_API_BASE_URL=\n"
        "KRX_API_KEY=unit-test-secret-value\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("KRX_") and not key.startswith("HARNESS_BATCH_KRX_")
    }
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "capture_krx_source_governance.py"),
            "--env-file",
            str(env_file),
            "--output",
            str(output),
            "--latest",
            str(latest),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 1
    assert output.exists()
    assert latest.exists()
    latest_text = latest.read_text(encoding="utf-8")
    payload = json.loads(latest_text)
    assert payload["authorization_status"] == "BLOCKED"
    assert payload["source_policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert payload["secret_redacted"] is True
    assert "unit-test-secret-value" not in latest_text


def test_serviceable_batch_artifact_builder_requires_postgres17_redis_and_lineage() -> None:
    module = _load_script_module(
        "capture_serviceable_top200_30d_artifact",
        "scripts/capture_serviceable_top200_30d_artifact.py",
    )
    coverage_row = {
        "universe_code": "DOMESTIC_TOP200_MARKET_CAP",
        "as_of_date": "2026-05-15",
        "resolved_trading_date": "2026-05-15",
        "source_code": "KRX",
        "source_policy_code": "OFFICIAL_KRX_APPROVED",
        "target_size": 200,
        "selected_count": 200,
        "expected_member_days": 4000,
        "observed_member_days": 4000,
        "missing_member_days": 0,
        "covered_tickers": 200,
        "coverage_ratio": Decimal("1.0"),
        "expected_trading_days_by_market": {"KOSPI": 20, "KOSDAQ": 20},
    }
    provider_rows = [
        {"provider_code": "KRX", "provider_status_code": "PROVIDER_DONE", "rows_collected": 4000},
        {"provider_code": "DART", "provider_status_code": "PROVIDER_DONE", "rows_collected": 1},
        {"provider_code": "ECOS", "provider_status_code": "PROVIDER_DONE", "rows_collected": 1},
    ]
    ready = module.build_artifact(
        now=datetime(2026, 5, 16, tzinfo=UTC),
        postgres_version="17.4",
        coverage_row=coverage_row,
        provider_rows=provider_rows,
        synthetic_provider_rows=0,
        redis={"status_code": "READY", "ping": True, "lock_acquired": True, "lock_released": True},
        universe_code="DOMESTIC_TOP200_MARKET_CAP",
    )

    assert ready["passed"] is True
    assert ready["redis_ping"] is True
    assert ready["top200_coverage"]["selected_count"] == 200
    assert ready["top200_coverage"]["missing_member_days"] == 0
    assert ready["provider_summary"] == {"is_synthetic": False}

    blocked = module.build_artifact(
        now=datetime(2026, 5, 16, tzinfo=UTC),
        postgres_version="16.9",
        coverage_row=coverage_row | {"missing_member_days": 1, "coverage_ratio": Decimal("0.999")},
        provider_rows=provider_rows[:1],
        synthetic_provider_rows=1,
        redis={"status_code": "BLOCKED", "ping": False},
        universe_code="DOMESTIC_TOP200_MARKET_CAP",
    )

    assert blocked["passed"] is False
    assert "PostgreSQL 17 is required" in "\n".join(blocked["errors"])
    assert "Redis ping/lock readiness is required" in blocked["errors"]
    assert blocked["provider_summary"] == {"is_synthetic": True}


def _subprocess_env_without_live_connections() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DATABASE_URL",
            "REDIS_URL",
            "REDIS_HOST",
            "REDIS_PORT",
            "REDIS_PASSWORD",
            "REDIS_SENTINEL_HOSTS",
            "REDIS_SENTINEL_SERVICE_NAME",
        }
    }
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}"
    return env


def test_serviceable_batch_capture_db_failure_writes_failed_latest_without_secret(
    tmp_path,
) -> None:
    output = tmp_path / "serviceable-top200-30d.json"
    latest = tmp_path / "serviceable-top200-30d-latest.json"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://unit:unit-test-db-password@127.0.0.1:1/harness\n"
        "REDIS_URL=redis://:unit-test-redis-password@127.0.0.1:1/0\n"
        "REDIS_SOCKET_CONNECT_TIMEOUT=0.1\n"
        "REDIS_SOCKET_TIMEOUT=0.1\n"
    )
    env = _subprocess_env_without_live_connections()
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "capture_serviceable_top200_30d_artifact.py"),
            "--env-file",
            str(env_file),
            "--output",
            str(output),
            "--latest",
            str(latest),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 1
    assert output.exists()
    assert latest.exists()
    latest_text = latest.read_text(encoding="utf-8")
    payload = json.loads(latest_text)
    assert payload["status_code"] == "BLOCKED"
    assert payload["passed"] is False
    assert payload["top200_coverage"]["status_code"] == "BLOCKED"
    assert payload["postgres"]["status_code"] == "BLOCKED"
    assert payload["capture_error"]["stage"] == "postgres-read"
    assert "PostgreSQL capture failed" in "\n".join(payload["errors"])
    assert "unit-test-db-password" not in latest_text
    assert "unit-test-redis-password" not in latest_text


def test_data_readiness_capture_db_failure_writes_failed_latest_without_secret(tmp_path) -> None:
    output = tmp_path / "data-readiness.json"
    latest = tmp_path / "data-readiness-latest.json"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://unit:unit-test-readiness-password@127.0.0.1:1/harness\n"
    )
    env = _subprocess_env_without_live_connections()
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "capture_data_readiness.py"),
            "--env-file",
            str(env_file),
            "--output",
            str(output),
            "--latest",
            str(latest),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 1
    assert output.exists()
    assert latest.exists()
    latest_text = latest.read_text(encoding="utf-8")
    payload = json.loads(latest_text)
    assert payload["capture_status_code"] == "BLOCKED"
    assert payload["status_code"] == "BLOCKED"
    assert payload["domestic_market"]["status_code"] == "BLOCKED"
    assert payload["domestic_market"]["top200_coverage"]["status_code"] == "BLOCKED"
    assert payload["capture_error"]["stage"] == "postgres-read"
    assert "PostgreSQL readiness capture failed" in "\n".join(payload["errors"])
    assert "provider.dart_parseable_documents" in latest_text
    assert "provider.ecos_parseable_rows" in latest_text
    assert "unit-test-readiness-password" not in latest_text
