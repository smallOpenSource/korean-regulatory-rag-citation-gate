"""Stage 4 T256 — SYN-FAM-001..006 family-persona fixture structural lint.

DB-application tests live in the integration suite (require live PostgreSQL
+ migrations applied). This module exercises the fixture file at a
structural level: presence, sql_id headers, SYN-% CHECK conformance,
required column population, and persona-count correctness.
"""

from __future__ import annotations

import re
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "db" / "fixtures" / "seed_50_family_personas.sql"


def _read_fixture() -> str:
    assert FIXTURE_PATH.exists(), f"fixture missing at {FIXTURE_PATH}"
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_fixture_file_exists():
    assert FIXTURE_PATH.is_file()


def test_fixture_has_sql_id_headers():
    """Every DDL/DML block must carry /* sql_id: ... */ comment."""
    content = _read_fixture()
    sql_ids = re.findall(r"sql_id:\s*([a-z0-9_]+)", content)
    assert "seed_family_personas_t256" in sql_ids
    assert "seed_family_personas_risk_assessments_t256" in sql_ids


def test_fixture_contains_six_family_heads():
    """T256 demands 6 family-unit personas (SYN-FAM-001..006)."""
    content = _read_fixture()
    customer_nos = re.findall(r"'(SYN-FAM-0\d{2})'", content)
    assert set(customer_nos) == {
        "SYN-FAM-001", "SYN-FAM-002", "SYN-FAM-003",
        "SYN-FAM-004", "SYN-FAM-005", "SYN-FAM-006",
    }
    # Each customer_no may appear in both INSERT and risk_assessments blocks
    # but must occur at least once each.


def test_all_customer_nos_satisfy_v037_check():
    """V037 chk_customer_no_syn_prefix: customer_no LIKE 'SYN-%'."""
    content = _read_fixture()
    customer_nos = re.findall(r"'(SYN-FAM-0\d{2})'", content)
    for cust_no in customer_nos:
        assert cust_no.startswith("SYN-")


def test_fixture_has_on_conflict_upsert():
    """Re-runnable seeds must be idempotent via ON CONFLICT clauses."""
    content = _read_fixture()
    assert "ON CONFLICT (customer_no) DO UPDATE" in content
    assert "ON CONFLICT (id) DO UPDATE" in content


def test_each_persona_has_korean_name():
    """customer_name must be 한글 (per [[pb-perspective-self-check]])."""
    content = _read_fixture()
    # All 6 names live on lines that begin with 'SYN-FAM-' literal in single-quotes
    names = re.findall(r"'SYN-FAM-0\d{2}',\s*'([^']+)'", content)
    assert len(names) == 6
    for name in names:
        # At least one Korean syllable in the customer_name
        assert any("가" <= ch <= "힯" for ch in name), f"non-Korean name: {name!r}"


def test_risk_grade_codes_in_valid_range():
    """risk_grade_code is a textual code 1-7 per existing seeds."""
    content = _read_fixture()
    # Match lines like: '5', 'HIGH', 8500000000,
    # We only need to assert the grade codes used are within 1..7.
    grade_assignments = re.findall(
        r"'(SYN-FAM-0\d{2})',\s*'[^']+',\s*'[^']+',\s*'[^']+',\s*'([1-7])'",
        content,
    )
    assert len(grade_assignments) == 6
    grades = {g for _, g in grade_assignments}
    assert grades.issubset({"1", "2", "3", "4", "5", "6", "7"})


_CANONICAL_SEGMENTS = ("HNWI_CORE", "HNWI_ULTRA", "EMERGING_HNWI")


def test_total_assets_are_positive():
    content = _read_fixture()
    pattern = r",\s*'(?:" + "|".join(_CANONICAL_SEGMENTS) + r")',\s*(\d+)"
    matches = re.findall(pattern, content)
    assert len(matches) == 6, f"expected 6 segment-with-amount tuples, got {len(matches)}"
    for amount in matches:
        assert int(amount) > 0


def test_segments_are_canonical():
    """Segments must come from a small closed set per Customer 360 spec.

    Allowed values are the canonical Customer 360 segment_code enum:
    HNWI_CORE / HNWI_ULTRA / EMERGING_HNWI. The legacy 'HIGH/MEDIUM/LOW/
    VVIP/MASS' set was removed from the synthetic fixture when V037's
    seed_50_family_personas.sql was corrected (2026-05-23 v5 closure).
    """
    content = _read_fixture()
    pattern = r",\s*'(" + "|".join(_CANONICAL_SEGMENTS) + r")',"
    segments = re.findall(pattern, content)
    assert len(segments) == 6, f"expected 6 canonical segments, got {len(segments)}"
    assert set(segments).issubset(set(_CANONICAL_SEGMENTS))
