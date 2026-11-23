"""Batch runner contract tests."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import date

from apps.api.harness.batch import runner
from apps.api.harness.batch.jobs import (
    BatchProviderEvidence,
    provider_status_from_batch_log,
)
from apps.api.harness.batch.providers import KrxMarketTarget, KrxOfficialMarketTarget
from apps.api.harness.core.sql import validate_sql_text
from apps.api.harness.repositories import batch as batch_repo


@contextmanager
def temporary_env(updates: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_parse_stage_list_preserves_canonical_order_and_rejects_unknown() -> None:
    assert runner.parse_stage_list("provider,seed,provider") == ("seed", "provider")
    assert runner.parse_stage_list("all") == runner.DEFAULT_STAGES

    try:
        runner.parse_stage_list("seed,unknown")
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:  # pragma: no cover - failure branch only
        raise AssertionError("unknown stage accepted")


def test_runner_summary_keeps_provider_skipped_separate_from_local_success() -> None:
    result = runner.summarize_results(
        [
            runner.StageResult(
                stage="seed",
                status_code="DONE",
                job_name="seed-full-mvp",
                job_type_code="SEED_PROFILE",
                rows_collected=100,
                local_mandatory=True,
            ),
            runner.StageResult(
                stage="provider-broker",
                status_code="SKIPPED",
                job_name="provider-broker-market-prices",
                job_type_code="PROVIDER_BROKER",
                rows_skipped=1,
                provider_evidence=True,
                error_message="missing provider configuration: BROKER_BASE_URL",
            ),
        ]
    )

    assert result.status_code == "DEGRADED"
    assert result.local_status_code == "DONE"
    assert result.provider_status_code == "SKIPPED"
    assert result.provider_required_status_code == "NOT_RUN"
    assert result.exit_code(strict_external=False, provider_strictness="required") == 0
    assert result.exit_code(strict_external=False, provider_strictness="all") == 2
    assert result.exit_code(strict_external=True) == 2


def test_runner_strict_external_resolves_production_and_explicit_overrides() -> None:
    with temporary_env({"HARNESS_PROVIDER_STRICT": None, "HARNESS_PROVIDER_STRICTNESS": None}):
        assert runner.resolve_strict_external(explicit=None, app_env="development") is False
        assert runner.resolve_strict_external(explicit=None, app_env="production") is True
        assert runner.resolve_strict_external(explicit=True, app_env="development") is True
        assert runner.resolve_strict_external(explicit=False, app_env="production") is False
        assert (
            runner.resolve_provider_strictness(explicit=None, strict_external=False) == "required"
        )
        assert runner.resolve_provider_strictness(explicit=None, strict_external=True) == "all"
        assert (
            runner.resolve_provider_strictness(explicit="required", strict_external=True)
            == "required"
        )

    with temporary_env({"HARNESS_PROVIDER_STRICT": "true"}):
        assert runner.resolve_strict_external(explicit=None, app_env="development") is True
    with temporary_env({"HARNESS_PROVIDER_STRICT": "false"}):
        assert runner.resolve_strict_external(explicit=None, app_env="development") is False
        assert runner.resolve_strict_external(explicit=None, app_env="production") is True
    with temporary_env({"HARNESS_PROVIDER_STRICTNESS": "all"}):
        assert runner.resolve_provider_strictness(explicit=None, strict_external=False) == "all"


def test_embedding_batch_size_uses_cli_override_or_env() -> None:
    with temporary_env({"BGE_EMBEDDING_BATCH_SIZE": "7"}):
        assert runner.resolve_embedding_batch_size(None) == 7
        assert runner.resolve_embedding_batch_size(3) == 3


def test_runner_summary_fails_non_done_local_mandatory_stage() -> None:
    result = runner.summarize_results(
        [
            runner.StageResult(
                stage="transform",
                status_code="FAILED",
                job_name="document-transform",
                job_type_code="DOCUMENT_TRANSFORM",
                rows_failed=1,
                local_mandatory=True,
                error_message="raw document transform failed",
            )
        ]
    )

    assert result.status_code == "FAILED"
    assert result.local_status_code == "FAILED"
    assert result.exit_code(strict_external=False) == 1


def test_provider_strictness_required_blocks_required_provider_failures_only() -> None:
    result = runner.summarize_results(
        [
            runner.StageResult(
                stage="provider",
                status_code="SKIPPED",
                job_name="broker_market_collector",
                job_type_code="PROVIDER_BROKER",
                provider_evidence=True,
            ),
            runner.StageResult(
                stage="provider",
                status_code="SKIPPED",
                job_name="krx_market_collector",
                job_type_code="PROVIDER_KRX",
                provider_evidence=True,
            ),
        ]
    )

    assert result.status_code == "FAILED"
    assert result.provider_status_code == "SKIPPED"
    assert result.provider_required_status_code == "SKIPPED"
    assert result.exit_code(strict_external=False, provider_strictness="required") == 2


def test_runner_sql_has_sql_id() -> None:
    for name in (
        "COUNT_ACTIVE_HOUSE_VIEWS_SQL",
        "LIST_ACTIVE_DART_SECURITY_TARGETS_SQL",
        "GET_LATEST_KRX_TRADING_DAY_SQL",
    ):
        result = validate_sql_text(getattr(runner, name), context=f"runner.{name}")
        assert result.ok, result.errors


def test_provider_evidence_sql_and_taxonomy_contracts() -> None:
    expected_statuses = {
        "PROVIDER_DONE",
        "PROVIDER_NO_DATA",
        "PROVIDER_SKIPPED_CONFIG",
        "PROVIDER_SKIPPED_DISABLED",
        "PROVIDER_FAILED_AUTH",
        "PROVIDER_FAILED_RATE_LIMIT",
        "PROVIDER_FAILED_SCHEMA",
        "PROVIDER_FAILED_NETWORK",
    }

    assert set(batch_repo.PROVIDER_STATUS_CODES) == expected_statuses
    for sql_name in (
        "INSERT_BATCH_PROVIDER_EVIDENCE_SQL",
        "LIST_BATCH_PROVIDER_EVIDENCE_FOR_LOGS_SQL",
    ):
        sql_text = getattr(batch_repo, sql_name)
        result = validate_sql_text(sql_text, context=f"batch_repo.{sql_name}")
        assert result.ok, result.errors


def test_provider_batch_log_mapping_keeps_no_data_separate_from_failure() -> None:
    assert (
        provider_status_from_batch_log(
            {"status_code": "DONE", "rows_collected": 0, "rows_skipped": 1}
        )
        == "PROVIDER_NO_DATA"
    )
    assert (
        provider_status_from_batch_log(
            {"status_code": "SKIPPED", "error_message": "collector is disabled"}
        )
        == "PROVIDER_SKIPPED_DISABLED"
    )
    assert (
        provider_status_from_batch_log(
            {"status_code": "FAILED", "error_message": "HTTP 429 rate limit"}
        )
        == "PROVIDER_FAILED_RATE_LIMIT"
    )
    evidence = BatchProviderEvidence(
        provider_code="ECOS",
        provider_status_code="PROVIDER_NO_DATA",
        target_ref="ECOS:731Y001:D:base_rate",
        rows_skipped=1,
        provider_detail={"official_code": "INFO-200"},
    )
    assert evidence.provider_status_code == "PROVIDER_NO_DATA"


def test_provider_target_parsers_use_env_without_secrets() -> None:
    updates = {
        "HARNESS_BATCH_BROKER_TICKERS": "005930, 000660",
        "HARNESS_BATCH_ECOS_START_DATE": "2026-05-01",
        "HARNESS_BATCH_ECOS_END_DATE": "20260515",
        "HARNESS_BATCH_ECOS_TARGETS_JSON": None,
        "ECOS_ITEM_CODES": "0101000, 0102000",
        "HARNESS_BATCH_DART_BEGIN_DATE": "2026-05-01",
        "HARNESS_BATCH_DART_END_DATE": "20260515",
        "HARNESS_BATCH_DART_CORP_CODES": "00126380,00164779",
        "HARNESS_BATCH_DART_TARGETS_JSON": None,
        "HARNESS_BATCH_DART_PAGE_COUNT": "100",
        "HARNESS_BATCH_KRX_START_DATE": "2026-05-01",
        "HARNESS_BATCH_KRX_END_DATE": "20260515",
        "HARNESS_BATCH_KRX_TICKERS": "005930,000660",
        "HARNESS_BATCH_KRX_SOURCE": "PYKRX",
        "HARNESS_BATCH_KRX_MARKETS": "KOSPI,KOSDAQ",
        "HARNESS_BATCH_KRX_UNIVERSE_CODE": None,
        "HARNESS_BATCH_LOOKBACK_DAYS": None,
        "HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON": """[
          {
            "path": "/getBondPriceInfo",
            "query": {"numOfRows": 10},
            "ticker_field": "isinCd",
            "date_field": "basDt",
            "close_field": "clpr"
          }
        ]""",
    }
    with temporary_env(updates):
        assert runner.csv_values("HARNESS_BATCH_BROKER_TICKERS") == ("005930", "000660")
        assert runner.env_date("HARNESS_BATCH_ECOS_START_DATE", date(2026, 1, 1)) == date(
            2026, 5, 1
        )
        ecos_targets = runner.parse_ecos_targets()
        assert ecos_targets[0].statistic_code == "722Y001"
        assert ecos_targets[0].start == "20260501"
        assert ecos_targets[0].end == "20260515"
        assert ecos_targets[0].item_codes == ("0101000", "0102000")
        data_go_kr_targets = runner.parse_data_go_kr_targets()
        assert data_go_kr_targets[0].ticker_field == "isinCd"
        dart_targets = runner.parse_dart_targets()
        assert [target.corp_code for target in dart_targets] == ["00126380", "00164779"]
        assert dart_targets[0].page_count == 100
        krx_targets = runner.parse_krx_targets()
        assert krx_targets[0].start_date == "20260501"
        assert krx_targets[0].end_date == "20260515"
        assert [target.ticker for target in krx_targets] == ["005930", "000660"]
        official_targets = runner.parse_krx_official_targets()
        assert official_targets[0].market_code == "KOSPI"
        assert official_targets[0].bas_dd == "20260501"
        assert official_targets[0].ticker_filter == ("005930", "000660")
        assert official_targets[-1].market_code == "KOSDAQ"
        assert official_targets[-1].bas_dd == "20260515"


def test_krx_targets_use_batch_lookback_and_as_of_when_env_dates_absent() -> None:
    updates = {
        "HARNESS_BATCH_KRX_START_DATE": None,
        "HARNESS_BATCH_KRX_END_DATE": None,
        "HARNESS_BATCH_LOOKBACK_DAYS": None,
        "HARNESS_BATCH_KRX_LOOKBACK_DAYS": None,
        "HARNESS_BATCH_KRX_TICKERS": "005930",
        "HARNESS_BATCH_KRX_UNIVERSE_CODE": None,
    }

    with temporary_env(updates):
        targets = runner.parse_krx_targets(
            today=date(2026, 5, 16),
            default_trading_day=date(2026, 5, 15),
            lookback_days=30,
        )

    assert targets[0].start_date == "20260415"
    assert targets[0].end_date == "20260515"


def test_krx_targets_prefer_krx_specific_lookback() -> None:
    updates = {
        "HARNESS_BATCH_KRX_START_DATE": None,
        "HARNESS_BATCH_KRX_END_DATE": None,
        "HARNESS_BATCH_LOOKBACK_DAYS": "30",
        "HARNESS_BATCH_KRX_LOOKBACK_DAYS": "3",
        "HARNESS_BATCH_KRX_TICKERS": "005930",
        "HARNESS_BATCH_KRX_MARKETS": "KOSPI",
        "HARNESS_BATCH_KRX_UNIVERSE_CODE": None,
    }

    with temporary_env(updates):
        pykrx_target = runner.parse_krx_targets(
            today=date(2026, 5, 16),
            default_trading_day=date(2026, 5, 15),
        )[0]
        official_target = runner.parse_krx_official_targets(
            today=date(2026, 5, 16),
            default_trading_day=date(2026, 5, 15),
        )[0]

    assert pykrx_target.start_date == "20260512"
    assert pykrx_target.end_date == "20260515"
    assert official_target.requested_window_start == "20260512"
    assert official_target.requested_window_end == "20260515"


def test_krx_source_policy_supports_official_and_pykrx_branches() -> None:
    disabled = runner.resolve_krx_source_policy(
        enabled=False,
        requested_source=None,
        policy_code=None,
        pykrx_available=True,
    )
    assert disabled.runnable is False
    assert disabled.detail()["source_policy_code"] == "KRX_BLOCKED"

    with temporary_env({"KRX_API_BASE_URL": None, "KRX_API_KEY": None}):
        official_missing_config = runner.resolve_krx_source_policy(
            enabled=True,
            requested_source="KRX",
            policy_code="OFFICIAL_KRX_APPROVED",
            pykrx_available=True,
        )
    assert official_missing_config.runnable is False
    assert official_missing_config.provider_status_code == "PROVIDER_SKIPPED_CONFIG"
    assert "KRX_API_KEY" in str(official_missing_config.reason)

    with temporary_env(
        {"KRX_API_BASE_URL": "https://data-dbg.krx.co.kr", "KRX_API_KEY": "unit-test-key"}
    ):
        official_approved = runner.resolve_krx_source_policy(
            enabled=True,
            requested_source="KRX",
            policy_code="OFFICIAL_KRX_APPROVED",
            pykrx_available=False,
        )
    official_detail = official_approved.detail()
    assert official_approved.runnable is True
    assert official_detail["source_code"] == "KRX"
    assert official_detail["source_official"] is True
    assert official_detail["source_policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert official_detail["source_label"] == "KRX 공식 OpenAPI"

    missing_policy = runner.resolve_krx_source_policy(
        enabled=True,
        requested_source="PYKRX",
        policy_code=None,
        pykrx_available=True,
    )
    assert missing_policy.runnable is False
    assert "PYKRX_AUXILIARY_APPROVED" in str(missing_policy.reason)

    missing_dependency = runner.resolve_krx_source_policy(
        enabled=True,
        requested_source="PYKRX",
        policy_code="PYKRX_AUXILIARY_APPROVED",
        pykrx_available=False,
    )
    assert missing_dependency.runnable is False
    assert missing_dependency.detail()["source_policy_code"] == "KRX_BLOCKED"

    approved = runner.resolve_krx_source_policy(
        enabled=True,
        requested_source="PYKRX",
        policy_code="PYKRX_AUXILIARY_APPROVED",
        pykrx_available=True,
    )
    detail = approved.detail()
    assert approved.runnable is True
    assert detail["source_code"] == "PYKRX"
    assert detail["source_label"] == "pykrx 비공식 보조 소스"
    assert detail["source_policy_code"] == "PYKRX_AUXILIARY_APPROVED"
    assert detail["source_official"] is False
    assert detail["t55_closure_wording"] == "T55 internal PoC READY with PYKRX_AUXILIARY"


def test_ecos_targets_json_supports_item_codes_and_rolling_windows() -> None:
    updates = {
        "HARNESS_BATCH_ECOS_START_DATE": None,
        "HARNESS_BATCH_ECOS_END_DATE": None,
        "ECOS_START": None,
        "ECOS_END": None,
        "ECOS_ITEM_CODES": None,
        "HARNESS_BATCH_ECOS_LOOKBACK_DAYS": "10",
        "HARNESS_BATCH_ECOS_DATE_LAG_DAYS": "1",
        "HARNESS_BATCH_ECOS_TARGETS_JSON": """[
          {
            "statistic_code": "731Y001",
            "cycle": "D",
            "indicator_name": "base_rate",
            "unit": "pct",
            "item_codes": ["0101000"],
            "lookback_days": 5
          },
          {
            "statistic_code": "036Y001",
            "cycle": "D",
            "indicator_name": "usd_krw",
            "unit": "krw",
            "item_codes": "0000001",
            "start": "2026-05-01",
            "end": "20260515"
          }
        ]""",
    }

    with temporary_env(updates):
        targets = runner.parse_ecos_targets(today=date(2026, 5, 16))

    assert len(targets) == 2
    assert targets[0].start == "20260510"
    assert targets[0].end == "20260515"
    assert targets[0].item_codes == ("0101000",)
    assert targets[0].lookback_days == 5
    assert targets[0].date_lag_days == 1
    assert targets[1].start == "20260501"
    assert targets[1].end == "20260515"
    assert targets[1].item_codes == ("0000001",)


def test_default_dart_target_window_is_wide_enough_for_recent_filings() -> None:
    updates: dict[str, str | None] = {
        "HARNESS_BATCH_DART_TARGETS_JSON": None,
        "HARNESS_BATCH_DART_CORP_CODES": None,
        "DART_CORP_CODE": None,
        "HARNESS_BATCH_DART_BEGIN_DATE": None,
        "HARNESS_BATCH_DART_END_DATE": None,
        "DART_BEGIN_DATE": None,
        "DART_END_DATE": None,
        "HARNESS_BATCH_DART_LOOKBACK_DAYS": None,
    }

    with temporary_env(updates):
        targets = runner.parse_dart_targets(today=date(2026, 5, 16))

    assert targets[0].corp_code == "00126380"
    assert targets[0].begin_date == "20250516"
    assert targets[0].end_date == "20260516"


def test_dart_targets_json_supports_stock_discovery_and_rolling_windows() -> None:
    updates = {
        "HARNESS_BATCH_DART_CORP_CODES": None,
        "DART_CORP_CODE": None,
        "HARNESS_BATCH_DART_BEGIN_DATE": None,
        "HARNESS_BATCH_DART_END_DATE": None,
        "HARNESS_BATCH_DART_LOOKBACK_DAYS": "90",
        "HARNESS_BATCH_DART_PAGE_COUNT": "50",
        "HARNESS_BATCH_DART_TARGETS_JSON": """[
          {"stock_code": "005930", "report_type": "A", "lookback_days": 30},
          {"corp_code": "00164779", "begin_date": "2026-01-01", "end_date": "20260515"}
        ]""",
    }

    with temporary_env(updates):
        targets = runner.parse_dart_targets(today=date(2026, 5, 15))

    assert len(targets) == 2
    assert targets[0].stock_code == "005930"
    assert targets[0].corp_code is None
    assert targets[0].begin_date == "20260415"
    assert targets[0].end_date == "20260515"
    assert targets[0].report_type == "A"
    assert targets[0].page_count == 50
    assert targets[1].corp_code == "00164779"
    assert targets[1].begin_date == "20260101"


def test_provider_contract_matrix_is_report_safe() -> None:
    matrix = runner.provider_contract_matrix()
    providers = {entry["provider_code"] for entry in matrix}

    assert {"BROKER", "OPENDART", "ECOS", "DATA_GO_KR", "KRX"} <= providers
    assert any("BROKER_APP_SECRET" in entry["required_env"] for entry in matrix)
    assert any("KRX_API_KEY" in entry["optional_env"] for entry in matrix)
    assert any("HARNESS_BATCH_KRX_SOURCE" in entry["optional_env"] for entry in matrix)
    assert all("api_key=" not in str(entry).lower() for entry in matrix)


def test_provider_window_report_includes_resolved_krx_window() -> None:
    result = runner.StageResult(
        stage="provider",
        status_code="DONE",
        job_name="krx_market_collector",
        job_type_code="PROVIDER_KRX",
        detail={
            "provider": "KRX",
            "windows": [
                runner.krx_target_report_window(KrxMarketTarget("005930", "20260415", "20260515"))
            ],
        },
        provider_evidence=True,
    )

    windows = runner.provider_window_report([result])

    assert windows == [
        {
            "provider": "KRX",
            "target_ref": "PYKRX:005930:20260415-20260515",
            "ticker": "005930",
            "requested_window_start": "2026-04-15",
            "requested_window_end": "2026-05-15",
            "source_policy": "AUXILIARY_HISTORICAL_DAILY_PRICE",
            "source_code": "PYKRX",
            "precedence_rank": 2,
        }
    ]


def test_provider_window_report_includes_official_krx_market_date_ref() -> None:
    result = runner.StageResult(
        stage="provider",
        status_code="DONE",
        job_name="krx_market_collector",
        job_type_code="PROVIDER_KRX",
        detail={
            "provider": "KRX",
            "windows": [
                runner.krx_official_target_report_window(
                    KrxOfficialMarketTarget(
                        "KOSPI", "20260515", ("005930",), "20260515", "20260515"
                    )
                )
            ],
        },
        provider_evidence=True,
    )

    windows = runner.provider_window_report([result])

    assert len(windows) == 1
    assert windows[0]["provider"] == "KRX"
    assert re.fullmatch(r"KRX:KOSPI:20260515:[0-9a-f]{12}", windows[0]["target_ref"])
    assert windows[0]["source_code"] == "KRX"
    assert windows[0]["source_policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert windows[0]["redacted_auth"] is True


def test_stage_report_marks_local_and_provider_evidence_separately() -> None:
    result = runner.StageResult(
        stage="provider",
        status_code="SKIPPED",
        job_name="broker_market_collector",
        job_type_code="PROVIDER_BROKER",
        rows_skipped=1,
        provider_evidence=True,
    )

    payload = result.as_dict()

    assert payload["provider_evidence"] is True
    assert payload["local_mandatory"] is False


def test_provider_window_report_includes_official_krx_window() -> None:
    with temporary_env(
        {
            "HARNESS_BATCH_KRX_START_DATE": None,
            "HARNESS_BATCH_KRX_END_DATE": None,
            "HARNESS_BATCH_LOOKBACK_DAYS": None,
            "HARNESS_BATCH_KRX_LOOKBACK_DAYS": None,
            "HARNESS_BATCH_KRX_TICKERS": "005930",
            "HARNESS_BATCH_KRX_MARKETS": "KOSPI",
            "HARNESS_BATCH_KRX_UNIVERSE_CODE": None,
        }
    ):
        target = runner.parse_krx_official_targets(
            today=date(2026, 5, 16),
            default_trading_day=date(2026, 5, 15),
            lookback_days=1,
        )[0]
    window = runner.krx_official_target_report_window(target)

    assert window["source_code"] == "KRX"
    assert window["source_policy"] == "OFFICIAL_DAILY_TRADING_PRICE"
    assert window["target_ref"].startswith("KRX:KOSPI:")
    assert window["ticker_filter_count"] == 1


def test_krx_official_targets_use_top200_universe_mode_without_static_ticker_filter() -> None:
    with temporary_env(
        {
            "HARNESS_BATCH_KRX_START_DATE": None,
            "HARNESS_BATCH_KRX_END_DATE": None,
            "HARNESS_BATCH_LOOKBACK_DAYS": None,
            "HARNESS_BATCH_KRX_LOOKBACK_DAYS": None,
            "HARNESS_BATCH_KRX_TICKERS": "005930",
            "HARNESS_BATCH_KRX_UNIVERSE_CODE": "DOMESTIC_TOP200_MARKET_CAP",
            "HARNESS_BATCH_KRX_UNIVERSE_SIZE": "200",
            "HARNESS_BATCH_KRX_UNIVERSE_MARKETS": "KOSPI,KOSDAQ",
            "HARNESS_BATCH_KRX_UNIVERSE_EXCLUDE_PREFERRED": "true",
        }
    ):
        targets = runner.parse_krx_official_targets(
            today=date(2026, 5, 16),
            default_trading_day=date(2026, 5, 15),
            lookback_days=2,
        )

    assert len(targets) == 6
    assert targets[0].bas_dd == "20260513"
    assert targets[-1].bas_dd == "20260515"
    assert {target.market_code for target in targets} == {"KOSPI", "KOSDAQ"}
    assert {target.ticker_filter for target in targets} == {()}
    assert {target.universe_code for target in targets} == {"DOMESTIC_TOP200_MARKET_CAP"}
    assert {target.universe_size for target in targets} == {200}
    assert runner.krx_official_target_report_window(targets[0])["target_ref"] == (
        "KRX:KOSPI:20260513:DOMESTIC_TOP200_MARKET_CAP"
    )
