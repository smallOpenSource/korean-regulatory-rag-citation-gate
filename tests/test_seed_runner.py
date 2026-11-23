"""Full-MVP seed runner and fixture contract checks."""

from __future__ import annotations

import re
from pathlib import Path

from db.migrator import split_sql_statements, validate_statement
from db.seed import READINESS_THRESHOLDS, load_profile_fixtures, profile_names

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "db" / "fixtures"
PROVIDER_SOURCE_CODES = ("BROKER", "FDR", "PYKRX", "ECOS", "DATA_GO_KR")
PROVIDER_DOCUMENT_TYPES = ("DART", "REG_PAGE", "RESEARCH", "WEB_SEARCH")
PLACEHOLDER_DISPLAY_PATTERNS = (
    "Synthetic PB",
    "Synthetic WM",
    "Synthetic Admin",
    "Synthetic Branch",
    "Synthetic Portfolio",
    "Synthetic Balanced",
    "Synthetic KI",
    "Synthetic Short",
    "Synthetic Global",
    "Synthetic Income",
    "Synthetic Term",
    "Synthetic USD",
)
GENERIC_CUSTOMER_DISPLAY_RE = re.compile(r"고객\s*\d{1,3}\b")
DISPLAY_PII_RE = re.compile(
    r"(\d{2,3}-\d{3,4}-\d{4}|\d{6}-[1-4]\d{6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)"
)
STABLE_FIXTURE_UUIDS = (
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222201",
    "33333333-3333-3333-3333-333333333301",
    "44444444-4444-4444-4444-444444444401",
    "66666666-6666-6666-6666-666666666301",
)


def _full_mvp_text() -> str:
    return "\n".join(fixture.path.read_text() for fixture in load_profile_fixtures("full-mvp"))


def _seed_customer_display_names() -> list[str]:
    """Extract the scenario-descriptor field from the customers seed.

    The fixture row shape is:
        ('<uuid>', 'SYN-CUST-NNN', '<korean_name>', '<scenario_descriptor>', ...)

    Per the customer-name fixture rebake (Wave-Audit-Defect-Fix D.4) the
    third column is the synthetic Korean person name and the **fourth**
    column is the scenario descriptor (e.g. '강남 은퇴소득 현금흐름 설계')
    that downstream UI surfaces as customer_name. This extractor pulls
    the fourth quoted field — the assertion suite below verifies the
    scenario descriptors end with one of the known descriptor suffixes.
    """
    customer_fixture = FIXTURE_DIR / "seed_10_customers_risk.sql"
    return re.findall(
        r"'SYN-CUST-\d{3}',\s*'[^']+',\s*'([^']+)'",
        customer_fixture.read_text(encoding="utf-8"),
    )


def _all_seed_fixture_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(FIXTURE_DIR.glob("seed_*.sql"))
    )


def test_seed_runner_exposes_full_mvp_profile_with_valid_sql():
    assert "full-mvp" in profile_names()

    fixtures = load_profile_fixtures("full-mvp")
    assert [fixture.path.name for fixture in fixtures] == [
        "seed_00_identity.sql",
        "seed_10_customers_risk.sql",
        "seed_20_products_portfolios.sql",
        "seed_30_workflows.sql",
        "seed_40_manual_rag.sql",
    ]
    assert sum(len(fixture.statements) for fixture in fixtures) >= 20

    for fixture in fixtures:
        for index, statement in enumerate(fixture.statements, start=1):
            validate_statement(statement, context=f"{fixture.path}:{index}")


def test_full_mvp_fixture_satisfies_operational_data_matrix():
    text = _full_mvp_text()

    assert text.count("SYN-CUST-") >= READINESS_THRESHOLDS["customers"]
    assert "customer_name" in text
    assert "강남 은퇴소득 현금흐름 설계" in text
    assert "부산 월지급 ELS 사후관리" in text
    assert "은퇴소득 방어형 현금흐름 포트폴리오" in text
    assert "지수연계 스텝다운 ELS" in text
    for sql_id in (
        "seed_full_mvp_risk_assessments",
        "seed_full_mvp_portfolios",
        "seed_workflows_nba_actions",
        "seed_workflows_aftercare_events",
        "seed_workflows_simulations",
        "seed_workflows_order_simulations",
        "seed_workflows_prune_obsolete_recommendation_simulations",
        "seed_workflows_prune_obsolete_order_simulations",
        "seed_workflows_audit_logs",
    ):
        assert sql_id in text
    assert "은퇴소득 방어형 현금흐름 포트폴리오" in text
    assert "원화 유동성 관리 랩" in text


def test_full_mvp_fixture_uses_korean_display_copy_for_user_facing_fields():
    target_text = "\n".join(
        (FIXTURE_DIR / fixture_name).read_text()
        for fixture_name in (
            "seed_00_identity.sql",
            "seed_10_customers_risk.sql",
            "seed_20_products_portfolios.sql",
        )
    )

    banned_display_phrases = (
        "Synthetic PB One",
        "Synthetic PB Two",
        "Synthetic Portfolio",
        "Synthetic Balanced Fund",
        "Synthetic KI Watch ELS",
    )
    for phrase in banned_display_phrases:
        assert phrase not in target_text
    assert "customer_name" in target_text
    assert "강남 은퇴소득 현금흐름 설계" in target_text
    assert "상속증여 현금흐름 신탁" in target_text


def test_full_mvp_customer_display_names_are_scenario_descriptors_not_numbered_placeholders():
    display_names = _seed_customer_display_names()

    assert len(display_names) >= READINESS_THRESHOLDS["customers"]
    assert len(display_names) == len(set(display_names))
    for display_name in display_names:
        assert not GENERIC_CUSTOMER_DISPLAY_RE.search(display_name)
        assert not DISPLAY_PII_RE.search(display_name)
        assert "SYN-CUST" not in display_name
        assert "Synthetic" not in display_name
        assert display_name.endswith(
            ("관리", "설계", "준비", "검토", "점검", "운용", "사후관리", "성장", "포트폴리오")
        )

    assert "강남 법인오너 단기 유동성 관리" in display_names
    assert "부산 은퇴 현금흐름 설계" in display_names
    assert "부산 월지급 ELS 사후관리" in display_names


def test_seed_fixtures_do_not_contain_numbered_customer_display_placeholders():
    text = _all_seed_fixture_text()

    assert not GENERIC_CUSTOMER_DISPLAY_RE.search(text)
    assert "강남 배당·멀티에셋 균형성장" in text
    assert "배당·멀티에셋 균형성장 포트폴리오" in text


def test_full_mvp_fixture_keeps_ids_deterministic_while_display_copy_changes():
    text = _full_mvp_text()
    lowered_text = text.lower()

    for random_id_expression in ("gen_random_uuid", "uuid_generate", "uuid4", "random()"):
        assert random_id_expression not in lowered_text
    for stable_uuid in STABLE_FIXTURE_UUIDS:
        assert stable_uuid in text
    assert "555555555300 + series_no" in text
    assert "565656560000 + portfolio_no * 10 + holding_slot" in text
    assert "3000 + recommendation_no" in text
    assert "3000 + order_no" in text
    assert "SYN-CUST-001" in text
    assert "강남 은퇴소득 현금흐름 설계" in text


def test_full_mvp_fixture_scenario_threads_are_coherent():
    text = _full_mvp_text()

    scenario_threads = {
        "inheritance_liquidity": (
            "강남 상속증여 현금흐름 준비",
            "상속증여 현금흐름 신탁",
            "상속세 유동성",
        ),
        "corporate_liquidity": (
            "강남 법인오너 단기 유동성 관리",
            "원화 유동성 관리 랩",
            "법인 유동성",
            "만기 분산",
        ),
        "retirement_cashflow": (
            "부산 은퇴 현금흐름 설계",
            "6개월 만기 정기예금",
            "현금흐름",
        ),
        "els_aftercare": (
            "부산 월지급 ELS 사후관리",
            "월지급식 고위험 ELS",
            "KI_TRIGGERED",
            "고위험 ELS knock-in",
        ),
    }
    for terms in scenario_threads.values():
        for term in terms:
            assert term in text

    assert "Korean PB/WM Scenario Portfolio" not in text
    assert "은퇴소득 방어형 현금흐름 포트폴리오" in text


def test_full_mvp_fixture_does_not_forge_provider_market_or_unstructured_rows():
    provider_literals = "|".join(PROVIDER_SOURCE_CODES)
    market_table_names = (
        "market_price_bars",
        "market_prices",
        "financial_ratios",
        "investor_flows",
        "macro_indicators",
    )

    for path in sorted(FIXTURE_DIR.glob("seed_*.sql")):
        for statement in split_sql_statements(path.read_text()):
            lower_statement = statement.lower()
            if any(table_name in lower_statement for table_name in market_table_names):
                assert not re.search(rf"'({provider_literals})'", statement)
            inserts_documents = (
                "insert into raw_documents" in lower_statement
                or "insert into documents" in lower_statement
            )
            if inserts_documents:
                for source_type in PROVIDER_DOCUMENT_TYPES:
                    assert f"'{source_type}'" not in statement


def test_full_mvp_fixture_records_blocked_provider_and_embedding_evidence_only():
    text = _full_mvp_text()

    assert "broker_market_collector" in text
    assert "dart_disclosure_collector" in text
    assert "bge_embedding_refresh" in text
    assert "'SKIPPED'" in text
    assert "Provider collector requires configured BROKER credentials" in text
    assert "Internal BGE not invoked by seed" in text
    assert "embedding = NULL" in text
    assert "is_embedded = FALSE" in text
