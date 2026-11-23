"""Canonical serviceable artifact producer contracts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from apps.api.harness.core.sql import validate_sql_text
from scripts import capture_krx_source_governance as governance
from scripts import run_serviceable_canonical_readiness as serviceable
from scripts import verify_serviceable_readiness as verifier


def _clear_krx_env(monkeypatch) -> None:  # noqa: ANN001 - pytest monkeypatch fixture
    for key in (
        "HARNESS_BATCH_KRX_ENABLED",
        "HARNESS_BATCH_KRX_SOURCE",
        "HARNESS_BATCH_KRX_POLICY",
        "KRX_API_BASE_URL",
        "KRX_API_KEY",
        "KRX_API_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_capture_krx_source_governance_refreshes_latest_only_for_real_official_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HARNESS_BATCH_KRX_ENABLED=true",
                "HARNESS_BATCH_KRX_SOURCE=KRX",
                "HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED",
                "KRX_API_BASE_URL=https://data.krx.example",
                "KRX_API_KEY=unit-test-krx-secret",
                "KRX_API_TIMEOUT_SECONDS=1",
            ]
        )
        + "\n"
    )
    _clear_krx_env(monkeypatch)

    def fake_requester(**kwargs):  # noqa: ANN001 - request_json-compatible test double
        assert kwargs["headers"] == {"AUTH_KEY": "unit-test-krx-secret"}
        assert "unit-test-krx-secret" not in kwargs["url"]
        return governance.JsonHttpResponse(
            status_code=200,
            payload={"OutBlock_1": [{"ISU_SRT_CD": "005930", "TDD_CLSPRC": "81000"}]},
        )

    result = governance.capture_krx_source_governance(
        env_file=env_file,
        output_dir=tmp_path,
        markets=("KOSPI",),
        probe_date="20260515",
        requester=fake_requester,
    )

    assert result.latest_refreshed is True
    assert result.latest_path.exists()
    report = json.loads(result.latest_path.read_text())
    assert report["authorization_status"] == "APPROVED"
    assert report["source_policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert report["secret_redacted"] is True
    assert report["endpoints"][0]["returned_row_count"] == 1
    assert "unit-test-krx-secret" not in result.latest_path.read_text()


def test_capture_krx_source_governance_refreshes_blocked_latest_for_missing_real_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HARNESS_BATCH_KRX_ENABLED=true",
                "HARNESS_BATCH_KRX_SOURCE=KRX",
                "HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED",
                "KRX_API_BASE_URL=https://data.krx.example",
                "KRX_API_KEY=unit-test-krx-secret",
            ]
        )
        + "\n"
    )
    _clear_krx_env(monkeypatch)

    def fake_requester(**kwargs):  # noqa: ANN001 - request_json-compatible test double
        return governance.JsonHttpResponse(status_code=200, payload={"OutBlock_1": []})

    result = governance.capture_krx_source_governance(
        env_file=env_file,
        output_dir=tmp_path,
        markets=("KOSPI",),
        probe_date="20260515",
        requester=fake_requester,
    )

    assert result.latest_refreshed is True
    assert result.artifact_path.exists()
    assert result.latest_path.exists()
    report = json.loads(result.latest_path.read_text())
    assert report["authorization_status"] == "BLOCKED"
    assert "at least one official KRX endpoint must return real rows" in report["errors"]


def test_serviceable_batch_artifact_refreshes_latest_only_when_complete(tmp_path: Path) -> None:
    complete_metrics = {
        "snapshot_id": "00000000-0000-0000-0000-000000000001",
        "universe_code": "DOMESTIC_TOP200_MARKET_CAP",
        "selected_count": 200,
        "target_size": 200,
        "expected_member_days": 4000,
        "observed_member_days": 4000,
        "missing_member_days": 0,
        "expected_trading_days": 20,
        "covered_tickers": 200,
        "coverage_ratio": Decimal("1.0"),
        "krx_provider_done": 3,
        "official_krx_policy_rows": 3,
        "official_krx_price_rows": 4000,
        "official_krx_trading_days": 20,
        "ecos_provider_done": 1,
        "opendart_provider_done": 1,
        "synthetic_krx_price_rows": 0,
        "ecos_parseable_rows": 1,
        "opendart_document_sources": 1,
        "opendart_document_chunks": 1,
    }
    artifact = serviceable.build_batch_artifact(
        metrics=complete_metrics,
        redis_evidence={"ping": True, "lock_acquired": True, "lock_released": True},
        batch_run_report=".omx/reports/batch/example.json",
        min_selected=200,
        required_coverage_ratio=Decimal("1.0"),
        generated_at="2026-05-16T00:00:00Z",
    )

    artifact_path, latest_path, latest_refreshed = serviceable.write_batch_artifact(
        artifact=artifact,
        output_dir=tmp_path,
        latest_name="serviceable-top200-30d-latest.json",
        min_selected=200,
        required_coverage_ratio=Decimal("1.0"),
    )

    assert artifact_path.exists()
    assert latest_path.exists()
    assert latest_refreshed is True
    latest = json.loads(latest_path.read_text())
    assert latest["source_code"] == "KRX"
    assert latest["source_policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert latest["top200_coverage"]["missing_member_days"] == 0
    assert latest["redis"]["status_code"] == "READY"
    assert latest["provider_summary"]["is_synthetic"] is False


def test_serviceable_batch_artifact_refreshes_blocked_latest_when_incomplete(
    tmp_path: Path,
) -> None:
    incomplete_artifact = serviceable.build_batch_artifact(
        metrics={
            "universe_code": "DOMESTIC_TOP200_MARKET_CAP",
            "selected_count": 199,
            "expected_member_days": 4000,
            "observed_member_days": 3999,
            "missing_member_days": 1,
            "coverage_ratio": Decimal("0.99975"),
            "synthetic_krx_price_rows": 0,
        },
        redis_evidence={"ping": True, "lock_acquired": True, "lock_released": True},
        batch_run_report=None,
        min_selected=200,
        required_coverage_ratio=Decimal("1.0"),
        generated_at="2026-05-16T00:00:00Z",
    )

    artifact_path, latest_path, latest_refreshed = serviceable.write_batch_artifact(
        artifact=incomplete_artifact,
        output_dir=tmp_path,
        latest_name="serviceable-top200-30d-latest.json",
        min_selected=200,
        required_coverage_ratio=Decimal("1.0"),
    )

    assert artifact_path.exists()
    assert latest_path.exists()
    assert latest_refreshed is True
    latest = json.loads(latest_path.read_text())
    assert latest["status_code"] == "BLOCKED"
    assert latest["passed"] is False


def test_serviceable_batch_artifact_sql_has_mandatory_sql_id() -> None:
    result = validate_sql_text(
        serviceable.SERVICEABLE_BATCH_ARTIFACT_SQL,
        context="serviceable.canonical_artifact_sql",
    )

    assert result.ok, result.errors
    assert (
        "capture_serviceable_top200_30d_batch_artifact"
        in serviceable.SERVICEABLE_BATCH_ARTIFACT_SQL
    )


def test_validator_default_docs_sync_includes_test_strategy_doc() -> None:
    assert "docs/test/TEST-01_test_strategy.md" in verifier.DEFAULT_DOC_SYNC_PATHS
    assert "docs/runbooks/OPS-03_troubleshooting.md" in verifier.DEFAULT_DOC_SYNC_PATHS
