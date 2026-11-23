"""AC11 + AC14 — SYN-FAM persona education marker and PB distribution lint.

Structural tests that run without a live DB:
  - Verify all 6 SYN-FAM customer_names carry the [교육용] prefix (AC11).
  - Verify surveyed_by_id is distributed across exactly 3 distinct PB ids,
    each assigned to exactly 2 personas (AC14).

Integration tests (require live PostgreSQL + migrations + fixtures applied)
are gated behind the ``integration`` marker and skipped automatically in
environments without a DB connection string.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture file path
# ---------------------------------------------------------------------------

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "fixtures"
    / "seed_50_family_personas.sql"
)

_SYN_FAM_CUSTOMER_NO_PATTERN = re.compile(r"'(SYN-FAM-0\d{2})'")
_CUSTOMER_NAME_PATTERN = re.compile(
    r"'SYN-FAM-0\d{2}',\s*'([^']+)'"
)
_SURVEYED_BY_PATTERN = re.compile(
    r"'33333333-3333-3333-4444-3333333ff0\d'.*?"
    r"'(22222222-2222-2222-2222-222222222\d{3})'",
    re.DOTALL,
)


def _read_fixture() -> str:
    assert FIXTURE_PATH.exists(), f"fixture missing at {FIXTURE_PATH}"
    return FIXTURE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC11 — [교육용] prefix on all SYN-FAM customer_names
# ---------------------------------------------------------------------------


def test_all_syn_fam_customer_names_have_education_marker():
    """AC11: every SYN-FAM customer_name must start with [교육용]."""
    content = _read_fixture()
    names = _CUSTOMER_NAME_PATTERN.findall(content)
    assert len(names) == 6, f"expected 6 customer_name entries, got {len(names)}: {names}"
    for name in names:
        assert name.startswith("[교육용]"), (
            f"customer_name missing [교육용] prefix: {name!r}"
        )
    print(f"AC11 verified: {len(names)} names all carry [교육용] prefix")
    for name in names:
        print(f"  {name!r}")


def test_education_marker_count_at_least_six():
    """AC11: grep-level check — at least 6 occurrences of [교육용] in the file."""
    content = _read_fixture()
    count = content.count("[교육용]")
    assert count >= 6, f"expected >=6 occurrences of [교육용], found {count}"
    print(f"AC11 grep count: {count} occurrences of [교육용]")


# ---------------------------------------------------------------------------
# AC14 — surveyed_by_id distributed across 3 PBs (2/2/2)
# ---------------------------------------------------------------------------


def test_surveyed_by_id_three_distinct_pbs():
    """AC14: risk_assessments block must reference exactly 3 distinct surveyed_by_id values."""
    content = _read_fixture()
    # Extract the risk_assessments INSERT block only
    ra_block_match = re.search(
        r"INSERT INTO risk_assessments.*?ON CONFLICT",
        content,
        re.DOTALL,
    )
    assert ra_block_match, "risk_assessments INSERT block not found"
    ra_block = ra_block_match.group(0)

    surveyed_ids = re.findall(
        r"'(22222222-2222-2222-2222-222222222\d{3})'",
        ra_block,
    )
    assert len(surveyed_ids) == 6, (
        f"expected 6 surveyed_by_id values, got {len(surveyed_ids)}: {surveyed_ids}"
    )

    distinct_ids = set(surveyed_ids)
    assert len(distinct_ids) == 3, (
        f"expected 3 distinct surveyed_by_id values, got {len(distinct_ids)}: {distinct_ids}"
    )
    print(f"AC14 verified: {len(distinct_ids)} distinct surveyed_by_id values")
    for pb_id in sorted(distinct_ids):
        print(f"  {pb_id}")


def test_surveyed_by_id_each_pb_assigned_two_personas():
    """AC14: each of the 3 PBs must be assigned exactly 2 risk assessments."""
    content = _read_fixture()
    ra_block_match = re.search(
        r"INSERT INTO risk_assessments.*?ON CONFLICT",
        content,
        re.DOTALL,
    )
    assert ra_block_match, "risk_assessments INSERT block not found"
    ra_block = ra_block_match.group(0)

    surveyed_ids = re.findall(
        r"'(22222222-2222-2222-2222-222222222\d{3})'",
        ra_block,
    )

    from collections import Counter
    distribution = Counter(surveyed_ids)
    print(f"AC14 PB distribution: {dict(distribution)}")

    for pb_id, count in distribution.items():
        assert count == 2, (
            f"PB {pb_id} has {count} assigned personas, expected 2"
        )


def test_pb_ids_201_202_203_all_present():
    """AC14: the three specific PB UUIDs ...201, ...202, ...203 must all appear."""
    content = _read_fixture()
    ra_block_match = re.search(
        r"INSERT INTO risk_assessments.*?ON CONFLICT",
        content,
        re.DOTALL,
    )
    assert ra_block_match, "risk_assessments INSERT block not found"
    ra_block = ra_block_match.group(0)

    expected_pbs = {
        "22222222-2222-2222-2222-222222222201",
        "22222222-2222-2222-2222-222222222202",
        "22222222-2222-2222-2222-222222222203",
    }
    for pb_id in expected_pbs:
        assert pb_id in ra_block, f"PB id {pb_id} not found in risk_assessments block"
    print(f"AC14 all 3 PB ids confirmed present: {expected_pbs}")


# ---------------------------------------------------------------------------
# Integration test (skipped without DB)
# ---------------------------------------------------------------------------

_DB_URL = os.environ.get("DATABASE_URL", "")


@pytest.mark.integration
@pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL not set — skipping live DB assertions")
def test_db_syn_fam_education_marker_and_pb_distribution():
    """Live DB: SELECT from customer_families and risk_assessments, assert AC11+AC14.

    sql_id: test_syn_fam_personas_education_marker_integration
    """
    import asyncio

    import asyncpg  # type: ignore[import]

    from tests._pg_retry import connect_with_retry

    async def _run() -> None:
        conn = await connect_with_retry(asyncpg, _DB_URL)
        try:
            # AC11: all SYN-FAM customer_names carry [교육용]
            rows = await conn.fetch(
                "/* sql_id: sel_syn_fam_education_marker */ "
                "SELECT customer_no, customer_name FROM customers "
                "WHERE customer_no LIKE 'SYN-FAM-%' ORDER BY customer_no"
            )
            print(f"DB query returned {len(rows)} SYN-FAM rows")
            for row in rows:
                print(f"  {row['customer_no']}: {row['customer_name']!r}")
            if len(rows) == 0:
                pytest.skip(
                    "DATABASE_URL set but SYN-FAM seed not applied — "
                    "run scripts/run_db_seed.py (or test_seed_integration full profile) first"
                )
            assert len(rows) == 6, f"expected 6 SYN-FAM personas, got {len(rows)}"
            for row in rows:
                assert "[교육용]" in row["customer_name"], (
                    f"[교육용] missing from {row['customer_no']}: {row['customer_name']!r}"
                )

            # AC14: 3 distinct surveyed_by_id, each with 2 rows
            ra_rows = await conn.fetch(
                "/* sql_id: sel_syn_fam_pb_distribution */ "
                "SELECT ra.surveyed_by_id, count(*) AS cnt "
                "FROM risk_assessments ra "
                "JOIN customers c ON c.id = ra.customer_id "
                "WHERE c.customer_no LIKE 'SYN-FAM-%' "
                "GROUP BY ra.surveyed_by_id ORDER BY ra.surveyed_by_id"
            )
            print(f"DB PB distribution ({len(ra_rows)} PBs):")
            for row in ra_rows:
                print(f"  {row['surveyed_by_id']}: {row['cnt']} personas")
            assert len(ra_rows) == 3, f"expected 3 distinct PBs, got {len(ra_rows)}"
            for row in ra_rows:
                assert row["cnt"] == 2, (
                    f"PB {row['surveyed_by_id']} has {row['cnt']} personas, expected 2"
                )
        finally:
            await conn.close()

    asyncio.run(_run())
