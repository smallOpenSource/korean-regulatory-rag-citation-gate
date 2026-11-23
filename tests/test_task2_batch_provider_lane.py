"""Task 2 Batch/Provider lane regression tests.

The tests exercise parser and static persistence contracts only. They do not
create provider-labelled DB rows from local data and do not replace provider
clients with local success paths.
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest

from apps.api.harness.batch.providers import (
    PROVIDER_SOURCE_CONTRACTS,
    BrokerQuoteTarget,
    DartFilingTarget,
    DataGoKrMarketTarget,
    EcosIndicatorTarget,
    KrxMarketTarget,
    KrxOfficialMarketTarget,
    dart_document_body_evidence,
    dart_list_evidence,
    ensure_dart_document_xml_success,
    krx_official_target_ref,
    krx_target_window_detail,
    parse_broker_quote_payload,
    parse_dart_corp_code_zip,
    parse_dart_filing_documents,
    parse_data_go_kr_market_payload,
    parse_ecos_macro_payload,
    parse_krx_market_payload,
    parse_krx_official_basic_info_payload,
    parse_krx_official_market_payload,
    select_krx_top_market_cap_universe,
)
from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.repositories import batch as batch_repo
from db.migrator import split_sql_statements, validate_statement

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_provider_repository_sql_contracts_include_macro_and_batch_logs():
    sql_constants = {
        name: value
        for name, value in vars(batch_repo).items()
        if name.endswith("_SQL") and isinstance(value, str)
    }

    assert "UPSERT_MACRO_INDICATOR_SQL" in sql_constants
    assert "GET_PORTFOLIO_VALUATION_FROM_BARS_SQL" in sql_constants
    for name, sql_text in sql_constants.items():
        for index, statement in enumerate(split_sql_statements(sql_text), start=1):
            validate_statement(statement, context=f"batch_repo.{name}:{index}")


def test_official_krx_migration_replaces_source_check_with_sql_ids():
    migration = (
        PROJECT_ROOT / "db" / "migrations" / "V016__official_krx_provider_readiness.sql"
    ).read_text()

    for index, statement in enumerate(split_sql_statements(migration), start=1):
        validate_statement(statement, context=f"V016:{index}")
    assert "chk_market_price_bars_source_code" in migration
    assert "source_code IN ('KRX', 'BROKER', 'DATA_GO_KR', 'PYKRX')" in migration
    assert "SELECT pg_constraint.conname" in migration
    assert "pg_get_constraintdef" in migration


def test_provider_source_contract_matrix_covers_live_collectors():
    contracts = {contract.provider_code: contract for contract in PROVIDER_SOURCE_CONTRACTS}

    assert set(contracts) == {"BROKER", "OPENDART", "ECOS", "DATA_GO_KR", "KRX"}
    assert contracts["BROKER"].persistence_target == "market_price_bars"
    assert contracts["DATA_GO_KR"].persistence_target == "market_price_bars"
    assert contracts["KRX"].persistence_target == "market_price_bars"
    assert contracts["KRX"].persisted_source_code == "KRX|PYKRX"
    assert "KRX_API_KEY" in contracts["KRX"].optional_env
    assert contracts["OPENDART"].persisted_source_code == "DART"
    assert contracts["ECOS"].persistence_target == "macro_indicators"
    assert contracts["DATA_GO_KR"].required_env == (
        "DATA_GO_KR_API_BASE_URL",
        "DATA_GO_KR_SERVICE_KEY_ENCODING",
    )
    assert contracts["KRX"].gate_env == "HARNESS_BATCH_KRX_ENABLED"
    assert all(contract.job_type_code.startswith("PROVIDER_") for contract in contracts.values())
    for contract in contracts.values():
        assert not any(name.startswith("VITE_") for name in contract.required_env)


def test_broker_quote_parser_requires_provider_price_fields():
    payload = {
        "output": {
            "stck_bsop_date": "20260515",
            "stck_oprc": "70,000",
            "stck_hgpr": "72,000",
            "stck_lwpr": "69,500",
            "stck_prpr": "71,000",
            "acml_vol": "1234567",
        }
    }

    row = parse_broker_quote_payload(
        payload=payload,
        target=BrokerQuoteTarget(ticker="005930"),
        fallback_date=date(2026, 5, 15),
    )

    assert row == {
        "ticker": "005930",
        "source_code": "BROKER",
        "price_date": date(2026, 5, 15),
        "open_price": Decimal("70000"),
        "high_price": Decimal("72000"),
        "low_price": Decimal("69500"),
        "close_price": Decimal("71000"),
        "volume": Decimal("1234567"),
    }
    with pytest.raises(ExternalProviderError, match="stck_prpr"):
        parse_broker_quote_payload(
            payload={"output": {}},
            target=BrokerQuoteTarget(ticker="005930"),
            fallback_date=date(2026, 5, 15),
        )


def test_ecos_macro_parser_maps_only_provider_rows_to_ecos_source_code():
    rows = parse_ecos_macro_payload(
        payload={"StatisticSearch": {"row": [{"TIME": "20260515", "DATA_VALUE": "3.250"}]}},
        target=EcosIndicatorTarget(
            statistic_code="731Y001",
            cycle="D",
            start="20260515",
            end="20260515",
            indicator_name="base_rate",
            unit="pct",
        ),
    )

    assert rows == [
        {
            "indicator_code": "731Y001",
            "indicator_name": "base_rate",
            "reference_date": date(2026, 5, 15),
            "value": Decimal("3.250"),
            "unit": "pct",
            "source_code": "ECOS",
        }
    ]


def test_ecos_macro_parser_accepts_redacted_live_base_rate_capture():
    payload = json.loads(
        (
            PROJECT_ROOT
            / "tests"
            / "fixtures"
            / "provider"
            / "ecos_statistic_search_722y001_base_rate_redacted.json"
        ).read_text()
    )

    rows = parse_ecos_macro_payload(
        payload=payload,
        target=EcosIndicatorTarget(
            statistic_code="722Y001",
            cycle="D",
            start="20260505",
            end="20260515",
            indicator_name="base_rate",
            unit="연%",
            item_codes=("0101000",),
        ),
    )

    assert len(rows) == 3
    assert rows[0]["indicator_code"] == "722Y001"
    assert rows[0]["indicator_name"] == "base_rate"
    assert rows[0]["reference_date"] == date(2026, 5, 5)
    assert rows[0]["value"] == Decimal("2.5")
    assert rows[0]["unit"] == "연%"
    assert {row["source_code"] for row in rows} == {"ECOS"}


def test_ecos_no_data_result_is_not_parser_failure_or_fabricated_row():
    target = EcosIndicatorTarget(
        statistic_code="731Y001",
        cycle="D",
        start="20260506",
        end="20260516",
        indicator_name="base_rate",
        unit="pct",
        item_codes=("0101000",),
    )

    rows = parse_ecos_macro_payload(
        payload={"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}},
        target=target,
    )

    assert rows == []

    with pytest.raises(ExternalProviderError, match="PROVIDER_FAILED_SCHEMA"):
        parse_ecos_macro_payload(
            payload={"RESULT": {"CODE": "ERROR-500", "MESSAGE": "unexpected format"}},
            target=target,
        )


def test_data_go_kr_market_parser_requires_configured_field_mapping():
    rows = parse_data_go_kr_market_payload(
        payload={
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {
                                "isinCd": "KR103501G662",
                                "basDt": "20260515",
                                "clpr": "10025.5",
                            }
                        ]
                    }
                }
            }
        },
        target=DataGoKrMarketTarget(
            path="/getStockPriceInfo",
            query={"numOfRows": 10},
            ticker_field="isinCd",
            date_field="basDt",
            close_field="clpr",
        ),
    )

    assert rows == [
        {
            "ticker": "KR103501G662",
            "source_code": "DATA_GO_KR",
            "price_date": date(2026, 5, 15),
            "open_price": None,
            "high_price": None,
            "low_price": None,
            "close_price": Decimal("10025.5"),
            "volume": None,
        }
    ]
    with pytest.raises(ExternalProviderError, match="domestic Korea equity"):
        parse_data_go_kr_market_payload(
            payload={
                "response": {
                    "body": {
                        "items": {
                            "item": [{"isinCd": "US5949181045", "basDt": "20260515", "clpr": "300"}]
                        }
                    }
                }
            },
            target=DataGoKrMarketTarget(
                path="/getForeignPriceInfo",
                query={"numOfRows": 10},
                ticker_field="isinCd",
                date_field="basDt",
                close_field="clpr",
            ),
        )


def test_krx_market_parser_maps_pykrx_rows_to_provider_source_code():
    rows = parse_krx_market_payload(
        payload={
            "날짜": "20260515",
            "시가": "70,000",
            "고가": "72,000",
            "저가": "69,500",
            "종가": "71,000",
            "거래량": "1234567",
        },
        target=KrxMarketTarget(ticker="005930", start_date="20260515", end_date="20260515"),
    )

    assert rows == [
        {
            "ticker": "005930",
            "source_code": "PYKRX",
            "price_date": date(2026, 5, 15),
            "open_price": Decimal("70000"),
            "high_price": Decimal("72000"),
            "low_price": Decimal("69500"),
            "close_price": Decimal("71000"),
            "volume": Decimal("1234567"),
        }
    ]


def test_krx_market_parser_preserves_pandas_like_multi_day_rows():
    class Row:
        def __init__(self, values: dict[str, str]) -> None:
            self.values = values

        def to_dict(self) -> dict[str, str]:
            return self.values

    class Frame:
        empty = False

        def iterrows(self):
            return iter(
                [
                    (
                        "2026-05-14 00:00:00",
                        Row(
                            {"시가": "69,000", "고가": "70,500", "저가": "68,500", "종가": "70,000"}
                        ),
                    ),
                    (
                        "2026-05-15 00:00:00",
                        Row(
                            {"시가": "70,000", "고가": "72,000", "저가": "69,500", "종가": "71,000"}
                        ),
                    ),
                ]
            )

    target = KrxMarketTarget(ticker="005930", start_date="20260514", end_date="20260515")
    rows = parse_krx_market_payload(payload=Frame(), target=target)
    detail = krx_target_window_detail(target=target, rows=rows, row_count=len(rows))

    assert [row["price_date"] for row in rows] == [date(2026, 5, 14), date(2026, 5, 15)]
    assert {row["source_code"] for row in rows} == {"PYKRX"}
    assert detail["requested_window_start"] == "2026-05-14"
    assert detail["requested_window_end"] == "2026-05-15"
    assert detail["effective_min_date"] == "2026-05-14"
    assert detail["effective_max_date"] == "2026-05-15"
    assert detail["trading_day_count"] == 2
    assert detail["source_policy"] == "AUXILIARY_HISTORICAL_DAILY_PRICE"


def test_krx_official_market_parser_maps_real_outblock_rows_to_official_source_code():
    target = KrxOfficialMarketTarget(
        market_code="KOSPI",
        bas_dd="20260515",
        ticker_filter=("005930",),
        requested_window_start="20260515",
        requested_window_end="20260515",
    )

    result = parse_krx_official_market_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_CD": "005930",
                    "BAS_DD": "20260515",
                    "TDD_OPNPRC": "70,000",
                    "TDD_HGPRC": "72,000",
                    "TDD_LWPRC": "69,500",
                    "TDD_CLSPRC": "71,000",
                    "ACC_TRDVOL": "1,234,567",
                },
                {
                    "ISU_CD": "000660",
                    "BAS_DD": "20260515",
                    "TDD_CLSPRC": "180,000",
                },
            ]
        },
        target=target,
    )

    assert result.raw_row_count == 2
    assert result.ticker_filter_count == 1
    assert result.rows_skipped == 0
    assert result.rows_failed == 0
    row = result.rows[0]
    assert row | {
        "raw_payload_hash": row["raw_payload_hash"],
        "company_key": row["company_key"],
        "company_key_source_code": row["company_key_source_code"],
    } == row
    assert {
        key: row[key]
        for key in (
            "ticker",
            "source_code",
            "price_date",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "market_code",
            "market_cap_krw",
            "listed_shares",
            "trading_value_krw",
        )
    } == {
        "ticker": "005930",
        "source_code": "KRX",
        "price_date": date(2026, 5, 15),
        "open_price": Decimal("70000"),
        "high_price": Decimal("72000"),
        "low_price": Decimal("69500"),
        "close_price": Decimal("71000"),
        "volume": Decimal("1234567"),
        "market_code": "KOSPI",
        "market_cap_krw": None,
        "listed_shares": None,
        "trading_value_krw": None,
    }


def test_krx_official_market_parser_prefers_short_code_and_preserves_isin():
    target = KrxOfficialMarketTarget(
        market_code="KOSPI",
        bas_dd="20260515",
        ticker_filter=("005930",),
        requested_window_start="20260515",
        requested_window_end="20260515",
    )

    result = parse_krx_official_market_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_CD": "KR7005930003",
                    "ISU_SRT_CD": "005930",
                    "ISU_ABBRV": "삼성전자",
                    "BAS_DD": "20260515",
                    "TDD_CLSPRC": "71,000",
                    "MKTCAP": "400,000,000,000,000",
                    "LIST_SHRS": "5,969,782,550",
                }
            ]
        },
        target=target,
    )

    assert result.rows_failed == 0
    assert result.rows_skipped == 0
    assert result.rows[0]["ticker"] == "005930"
    assert result.rows[0]["isin"] == "KR7005930003"
    assert result.rows[0]["company_key"] == "삼성전자"


def test_krx_official_market_parser_skips_non_matching_alphanumeric_codes():
    target = KrxOfficialMarketTarget(
        market_code="KOSPI",
        bas_dd="20260515",
        ticker_filter=("005930",),
        requested_window_start="20260515",
        requested_window_end="20260515",
    )

    result = parse_krx_official_market_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_CD": "00104K",
                    "BAS_DD": "20260515",
                    "ISU_NM": "CJ4우(전환)",
                    "TDD_CLSPRC": "189300",
                },
                {
                    "ISU_CD": "005930",
                    "BAS_DD": "20260515",
                    "TDD_CLSPRC": "71,000",
                },
            ]
        },
        target=target,
    )

    assert result.rows_failed == 0
    assert result.rows_skipped == 1
    assert [row["ticker"] for row in result.rows] == ["005930"]


def test_krx_official_parser_skips_zero_close_and_parses_basic_info():
    target = KrxOfficialMarketTarget(
        market_code="KOSPI",
        bas_dd="20260515",
        ticker_filter=("005930",),
        requested_window_start="20260515",
        requested_window_end="20260515",
    )

    result = parse_krx_official_market_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_CD": "005930",
                    "BAS_DD": "20260515",
                    "TDD_OPNPRC": "0",
                    "TDD_HGPRC": "0",
                    "TDD_LWPRC": "0",
                    "TDD_CLSPRC": "0",
                    "ACC_TRDVOL": "-",
                }
            ]
        },
        target=target,
    )
    assert result.rows == []
    assert result.rows_skipped == 1

    securities = parse_krx_official_basic_info_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_SRT_CD": "005930",
                    "ISIN_CODE": "KR7005930003",
                    "ISU_ABBRV": "삼성전자",
                    "LIST_DD": "19750611",
                }
            ]
        },
        market_code="KOSPI",
        ticker_filter=("005930",),
    )
    assert securities == [
        {
            "ticker": "005930",
            "isin": "KR7005930003",
            "security_name_kr": "삼성전자",
            "market_code": "KOSPI",
            "listed_at": date(1975, 6, 11),
        }
    ]


def test_krx_official_basic_info_parser_accepts_isu_cd_isin_for_foreign_listing():
    securities = parse_krx_official_basic_info_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_CD": "KR8840120008",
                    "ISU_SRT_CD": "950160",
                    "ISU_NM": "코오롱티슈진",
                    "ISU_ABBRV": "코오롱티슈진",
                    "LIST_DD": "20171106",
                }
            ]
        },
        market_code="KOSDAQ",
        ticker_filter=("950160",),
    )

    assert securities == [
        {
            "ticker": "950160",
            "isin": "KR8840120008",
            "security_name_kr": "코오롱티슈진",
            "market_code": "KOSDAQ",
            "listed_at": date(2017, 11, 6),
        }
    ]


def test_dart_parser_keeps_provider_lineage_without_query_secrets():
    documents = parse_dart_filing_documents(
        payload={
            "list": [
                {"rcept_no": "20260515000123", "corp_code": "00126380", "report_nm": "분기보고서"}
            ]
        },
        api_base_url="https://opendart.example.invalid",
    )

    assert len(documents) == 1
    assert documents[0]["source_type_code"] == "DART"
    assert (
        documents[0]["source_url"]
        == "https://opendart.example.invalid/api/document.xml?rcept_no=20260515000123"
    )
    assert "crtfc_key" not in documents[0]["source_url"]
    assert "00126380" in documents[0]["raw_text"]


def test_dart_no_data_status_maps_to_provider_no_data_without_rows():
    target = DartFilingTarget(
        corp_code="00126380",
        begin_date="20260215",
        end_date="20260515",
    )
    payload = {"status": "013", "message": "조회된 데이타가 없습니다."}

    assert (
        parse_dart_filing_documents(
            payload=payload,
            api_base_url="https://opendart.example.invalid",
        )
        == []
    )
    evidence = dart_list_evidence(payload=payload, target=target, corp_code="00126380")

    assert evidence.provider_status_code == "PROVIDER_NO_DATA"
    assert evidence.target_ref == "DART:00126380:20260215-20260515:all"
    assert evidence.reason_message == "조회된 데이타가 없습니다."


def test_dart_non_success_status_keeps_failure_taxonomy():
    target = DartFilingTarget(
        corp_code="00126380",
        begin_date="20260215",
        end_date="20260515",
    )
    evidence = dart_list_evidence(
        payload={"status": "020", "message": "사용한도를 초과하였습니다."},
        target=target,
        corp_code="00126380",
    )

    assert evidence.provider_status_code == "PROVIDER_FAILED_RATE_LIMIT"
    with pytest.raises(ExternalProviderError, match="PROVIDER_FAILED_RATE_LIMIT"):
        parse_dart_filing_documents(
            payload={"status": "020", "message": "사용한도를 초과하였습니다."},
            api_base_url="https://opendart.example.invalid",
        )


def test_dart_corp_code_zip_parser_maps_stock_codes_without_cache_files():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "CORPCODE.xml",
            """
            <result>
              <list>
                <corp_code>00126380</corp_code>
                <corp_name>삼성전자</corp_name>
                <stock_code>005930</stock_code>
              </list>
              <list>
                <corp_code>00164779</corp_code>
                <corp_name>SK하이닉스</corp_name>
                <stock_code>000660</stock_code>
              </list>
            </result>
            """,
        )

    mapping = parse_dart_corp_code_zip(buffer.getvalue())

    assert mapping == {"005930": "00126380", "000660": "00164779"}


def test_dart_document_xml_official_no_data_is_skipped_not_failed():
    assert ensure_dart_document_xml_success(
        "<document><title>real body</title></document>", receipt_no="1"
    )
    assert not ensure_dart_document_xml_success(
        "<result><status>013</status><message>조회된 데이타가 없습니다.</message></result>",
        receipt_no="20260515000123",
    )
    assert not ensure_dart_document_xml_success(
        "<result><status>014</status><message>파일이 존재하지 않습니다.</message></result>",
        receipt_no="20260514800518",
    )
    with pytest.raises(ExternalProviderError, match="PROVIDER_FAILED_AUTH"):
        ensure_dart_document_xml_success(
            "<result><status>010</status><message>등록되지 않은 키입니다.</message></result>",
            receipt_no="20260515000123",
        )


def test_dart_target_evidence_requires_document_xml_body_for_done_status():
    target = DartFilingTarget(
        corp_code="00126380",
        begin_date="20250516",
        end_date="20260516",
    )

    list_only = dart_document_body_evidence(
        target=target,
        corp_code="00126380",
        filing_rows=1,
        document_xml_bodies=0,
        rows_skipped=1,
    )
    with_body = dart_document_body_evidence(
        target=target,
        corp_code="00126380",
        filing_rows=1,
        document_xml_bodies=1,
        rows_collected=1,
    )

    assert list_only.provider_status_code == "PROVIDER_NO_DATA"
    assert list_only.reason_message
    assert list_only.provider_detail_json is not None
    assert list_only.provider_detail_json["document_xml_bodies"] == 0
    assert with_body.provider_status_code == "PROVIDER_DONE"
    assert with_body.rows_collected == 1


def test_batch_provider_sources_have_no_fixture_inserts_under_provider_codes():
    fixture_text = "\n".join(
        path.read_text() for path in (PROJECT_ROOT / "db" / "fixtures").glob("*.sql")
    )

    assert not re.search(r"INSERT\s+INTO\s+market_price_bars\b", fixture_text, re.IGNORECASE)
    assert not re.search(r"INSERT\s+INTO\s+market_prices\b", fixture_text, re.IGNORECASE)
    assert not re.search(r"INSERT\s+INTO\s+macro_indicators\b", fixture_text, re.IGNORECASE)

    source_codes: list[str] = []
    for match in re.finditer(
        r"INSERT\s+INTO\s+raw_documents\b.*?VALUES(?P<body>.*?)(?:ON\s+CONFLICT|;)",
        fixture_text,
        re.IGNORECASE | re.DOTALL,
    ):
        source_codes.extend(re.findall(r"\(\s*'[^']+'\s*,\s*'([^']+)'", match.group("body")))
    assert set(source_codes) <= {"MANUAL"}



def test_krx_official_parser_enriches_market_cap_fields_for_top200_universe():
    target = KrxOfficialMarketTarget(
        market_code="KOSPI",
        bas_dd="20260515",
        ticker_filter=(),
        requested_window_start="20260515",
        requested_window_end="20260515",
        universe_code="DOMESTIC_TOP200_MARKET_CAP",
        universe_size=2,
    )

    result = parse_krx_official_market_payload(
        payload={
            "OutBlock_1": [
                {
                    "ISU_CD": "005930",
                    "ISU_ABBRV": "삼성전자",
                    "BAS_DD": "20260515",
                    "TDD_OPNPRC": "70,000",
                    "TDD_HGPRC": "72,000",
                    "TDD_LWPRC": "69,500",
                    "TDD_CLSPRC": "71,000",
                    "ACC_TRDVOL": "1,234,567",
                    "ACC_TRDVAL": "87,654,321,000",
                    "MKTCAP": "420,000,000,000,000",
                    "LIST_SHRS": "5,969,782,550",
                    "CMPPREVDD_PRC": "1,000",
                    "FLUC_RT": "1.43",
                }
            ]
        },
        target=target,
    )

    assert result.rows[0]["security_name_kr"] == "삼성전자"
    assert result.rows[0]["market_cap_krw"] == Decimal("420000000000000")
    assert result.rows[0]["listed_shares"] == Decimal("5969782550")
    assert result.rows[0]["trading_value_krw"] == Decimal("87654321000")
    assert result.rows[0]["change_price"] == Decimal("1000")
    assert result.rows[0]["change_rate_pct"] == Decimal("1.43")
    assert result.rows[0]["company_key"] == "삼성전자"
    assert len(result.rows[0]["raw_payload_hash"]) == 64


def test_krx_top_market_cap_universe_filters_preferred_and_duplicates():
    rows = [
        {
            "ticker": "005935",
            "source_code": "KRX",
            "security_name_kr": "삼성전자우",
            "market_code": "KOSPI",
            "market_cap_krw": Decimal("500"),
            "company_key": "삼성전자",
            "company_key_source_code": "SECURITY_NAME_NORMALIZED",
            "raw_payload_hash": "a" * 64,
            "close_price": Decimal("100"),
        },
        {
            "ticker": "005930",
            "source_code": "KRX",
            "security_name_kr": "삼성전자",
            "market_code": "KOSPI",
            "market_cap_krw": Decimal("400"),
            "company_key": "삼성전자",
            "company_key_source_code": "SECURITY_NAME_NORMALIZED",
            "raw_payload_hash": "b" * 64,
            "close_price": Decimal("100"),
        },
        {
            "ticker": "000660",
            "source_code": "KRX",
            "security_name_kr": "SK하이닉스",
            "market_code": "KOSPI",
            "market_cap_krw": Decimal("300"),
            "company_key": "SK하이닉스",
            "company_key_source_code": "SECURITY_NAME_NORMALIZED",
            "raw_payload_hash": "c" * 64,
            "close_price": Decimal("100"),
        },
    ]

    candidates, members = select_krx_top_market_cap_universe(rows, target_size=2)

    assert [member["ticker"] for member in members] == ["005930", "000660"]
    excluded = {
        candidate["ticker"]: candidate for candidate in candidates if not candidate["included"]
    }
    assert excluded["005935"]["exclusion_reason_code"] == "PREFERRED_SHARE"
    assert candidates[0]["rank_before_filter"] == 1
    assert members[0]["rank_no"] == 1


def test_krx_official_target_ref_uses_universe_code_without_hashing():
    target = KrxOfficialMarketTarget(
        market_code="KOSPI",
        bas_dd="20260515",
        ticker_filter=(),
        requested_window_start="20260415",
        requested_window_end="20260515",
        universe_code="DOMESTIC_TOP200_MARKET_CAP",
        universe_size=200,
    )

    assert krx_official_target_ref(target) == "KRX:KOSPI:20260515:DOMESTIC_TOP200_MARKET_CAP"
