"""Serviceable top-200 readiness validator and payload contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from apps.api.harness.services.readiness import build_readiness_payload

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _serviceable_metrics() -> dict[str, object]:
    return {
        "active_customers": 20,
        "portfolios": 20,
        "active_house_views": 1,
        "embedded_chunks": 4,
        "pending_raw_documents": 0,
        "security_master_rows": 220,
        "accepted_price_bar_rows": 4400,
        "price_bar_count": 4400,
        "price_bar_rows": 4400,
        "quality_check_count": 4400,
        "quality_failed_count": 0,
        "market_quality_issues_recent": 0,
        "latest_price_bar_source_as_of": date.today().isoformat(),
        "latest_price_bar_provider_code": "KRX",
        "dart_raw_documents": 1,
        "dart_document_sources": 1,
        "dart_document_chunks": 1,
        "embedded_dart_document_chunks": 1,
        "dart_embedded_chunks": 1,
        "required_provider_migrations_applied": 7,
        "batch_provider_evidence_table_present": 1,
        "ecos_parseable_rows": 1,
        "ecos_provider_done": 1,
        "dart_provider_done": 1,
        "pykrx_price_bar_rows": 0,
        "official_krx_price_bar_rows": 4400,
        "krx_provider_done": 30,
        "official_krx_provider_done": 30,
        "official_krx_policy_rows": 30,
        "top200_universe_snapshot_count": 1,
        "top200_selected_count": 200,
        "top200_target_size": 200,
        "top200_expected_member_days": 4000,
        "top200_valid_member_days": 4000,
        "top200_missing_member_days": 0,
        "top200_as_of_date": date.today().isoformat(),
        "top200_resolved_trading_date": date.today().isoformat(),
        "top200_expected_trading_days_by_market": {"KOSPI": 20, "KOSDAQ": 20},
    }


def _source_governance_report() -> dict[str, object]:
    return {
        "authorization_status": "APPROVED",
        "source_name": "KRX official OpenAPI",
        "source_policy_code": "OFFICIAL_KRX_APPROVED",
        "api_base_url_host": "data-dbg.krx.co.kr",
        "key_env_name": "KRX_API_KEY",
        "secret_redacted": True,
        "checked_at": "2026-05-16T00:00:00Z",
        "checked_by": "unit-test",
        "operational_owner": "data-platform",
        "approved_use_summary": "local serviceability verification",
        "approved_until": None,
        "rate_limit_policy": "bounded test evidence",
        "terms_reference": "internal runbook",
        "failure_mode": "fail_closed",
        "endpoints": [
            {
                "path": "/svc/apis/sto/stk_bydd_trd",
                "market": "KOSPI",
                "probe_date": "20260515",
                "http_status": 200,
                "provider_status_code": "PROVIDER_DONE",
                "returned_row_count": 1,
                "evidence_hash": "abc123def456",
            }
        ],
    }


def _batch_report(
    top200: dict[str, object],
    *,
    redis_ping: bool = True,
    source_code: str = "KRX",
    source_policy_code: str = "OFFICIAL_KRX_APPROVED",
    provider_is_synthetic: bool = False,
) -> dict[str, object]:
    return {
        "redis_ping": redis_ping,
        "source_code": source_code,
        "source_policy_code": source_policy_code,
        "top200_coverage": top200,
        "provider_summary": {"is_synthetic": provider_is_synthetic},
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload))


def _strict_validator_command(
    *,
    governance_path: Path,
    batch_path: Path,
    readiness_path: Path,
    result_path: Path,
) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "verify_serviceable_readiness.py"),
        "--source-governance-report",
        str(governance_path),
        "--batch-report",
        str(batch_path),
        "--readiness-report",
        str(readiness_path),
        "--result-json",
        str(result_path),
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
    ]


def test_data_readiness_exposes_ready_top200_coverage(monkeypatch):
    monkeypatch.setenv("HARNESS_BATCH_KRX_ENABLED", "true")
    monkeypatch.setenv("HARNESS_BATCH_KRX_SOURCE", "KRX")
    monkeypatch.setenv("HARNESS_BATCH_KRX_POLICY", "OFFICIAL_KRX_APPROVED")
    monkeypatch.setenv("HARNESS_BATCH_KRX_UNIVERSE_CODE", "DOMESTIC_TOP200_MARKET_CAP")
    monkeypatch.setenv("HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO", "1.0")

    payload = build_readiness_payload(_serviceable_metrics())
    top200 = payload["domestic_market"]["top200_coverage"]
    checks = {check["check_code"]: check for check in payload["domestic_market"]["checks"]}

    assert payload["status_code"] == "READY"
    assert payload["domestic_market"]["status_code"] == "READY"
    assert top200["status_code"] == "READY"
    assert top200["selected_count"] == 200
    assert top200["missing_member_days"] == 0
    assert top200["coverage_ratio"] == 1.0
    assert checks["market.top200_universe"]["status_code"] == "READY"
    assert checks["market.top200_30d_coverage"]["status_code"] == "READY"


def test_serviceable_validator_writes_passed_autoresearch_result(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_BATCH_KRX_ENABLED", "true")
    monkeypatch.setenv("HARNESS_BATCH_KRX_SOURCE", "KRX")
    monkeypatch.setenv("HARNESS_BATCH_KRX_POLICY", "OFFICIAL_KRX_APPROVED")
    monkeypatch.setenv("HARNESS_BATCH_KRX_UNIVERSE_CODE", "DOMESTIC_TOP200_MARKET_CAP")
    monkeypatch.setenv("KRX_API_KEY", "unit-test-secret-value")

    readiness = build_readiness_payload(_serviceable_metrics())
    top200 = readiness["domestic_market"]["top200_coverage"]
    governance = _source_governance_report()
    batch = _batch_report(top200)

    governance_path = tmp_path / "governance.json"
    batch_path = tmp_path / "batch.json"
    readiness_path = tmp_path / "readiness.json"
    result_path = tmp_path / "result.json"
    _write_json(governance_path, governance)
    _write_json(batch_path, batch)
    _write_json(readiness_path, readiness)

    command = _strict_validator_command(
        governance_path=governance_path,
        batch_path=batch_path,
        readiness_path=readiness_path,
        result_path=result_path,
    )
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result_path.read_text())
    assert payload["status"] == "passed"
    assert payload["passed"] is True
    assert payload["coverage_ratio"] == 1.0
    assert payload["selected_count"] == 200
    assert payload["docs_sync"]["errors"] == []
    assert payload["docs_sync"]["matched_paths"]
    assert "unit-test-secret-value" not in result_path.read_text()


def test_serviceable_validator_fails_closed_when_canonical_inputs_are_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("KRX_API_KEY", "missing-artifact-secret")
    readiness = build_readiness_payload(_serviceable_metrics())

    for missing_name in ("krx-source-governance-latest.json", "serviceable-top200-30d-latest.json"):
        case_dir = tmp_path / missing_name
        case_dir.mkdir()
        governance_path = case_dir / "krx-source-governance-latest.json"
        batch_path = case_dir / "serviceable-top200-30d-latest.json"
        readiness_path = case_dir / "readiness.json"
        result_path = case_dir / "result.json"
        top200 = readiness["domestic_market"]["top200_coverage"]

        if missing_name != governance_path.name:
            _write_json(governance_path, _source_governance_report())
        if missing_name != batch_path.name:
            _write_json(batch_path, _batch_report(top200))
        _write_json(readiness_path, readiness)

        result = subprocess.run(
            _strict_validator_command(
                governance_path=governance_path,
                batch_path=batch_path,
                readiness_path=readiness_path,
                result_path=result_path,
            ),
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )

        assert result.returncode == 1
        payload = json.loads(result_path.read_text())
        assert payload["status"] == "failed"
        assert payload["passed"] is False
        assert any(
            "missing artifact" in error and missing_name in error for error in payload["errors"]
        )
        combined_output = result.stdout + result.stderr + result_path.read_text()
        assert "missing-artifact-secret" not in combined_output


def test_serviceable_validator_rejects_auxiliary_synthetic_or_redisless_batch(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("KRX_API_KEY", "batch-rejection-secret")
    readiness = build_readiness_payload(_serviceable_metrics())
    top200 = readiness["domestic_market"]["top200_coverage"]
    governance_path = tmp_path / "krx-source-governance-latest.json"
    batch_path = tmp_path / "serviceable-top200-30d-latest.json"
    readiness_path = tmp_path / "readiness.json"
    result_path = tmp_path / "result.json"

    _write_json(governance_path, _source_governance_report())
    _write_json(
        batch_path,
        _batch_report(
            top200,
            redis_ping=False,
            source_code="PYKRX",
            source_policy_code="PYKRX_AUXILIARY_APPROVED",
            provider_is_synthetic=True,
        ),
    )
    _write_json(readiness_path, readiness)

    result = subprocess.run(
        _strict_validator_command(
            governance_path=governance_path,
            batch_path=batch_path,
            readiness_path=readiness_path,
            result_path=result_path,
        ),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 1
    payload = json.loads(result_path.read_text())
    errors = "\n".join(payload["errors"])
    assert "Redis ping or lock readiness" in errors
    assert "source_code must be KRX" in errors
    assert "source_policy_code must be OFFICIAL_KRX_APPROVED" in errors
    assert "is_synthetic=true provider evidence" in errors
    assert "batch-rejection-secret" not in result.stdout + result.stderr + result_path.read_text()


def test_autoresearch_serviceable_contract_artifacts_exist():
    spec_dir = PROJECT_ROOT / ".omx" / "specs" / "autoresearch-service-readiness-top200-30d"

    assert (spec_dir / "mission.md").exists()
    assert (spec_dir / "sandbox.md").exists()
    assert "scripts/verify_serviceable_readiness.py" in (spec_dir / "mission.md").read_text()
    assert "--no-fabricated-provider-rows" in (spec_dir / "sandbox.md").read_text()
