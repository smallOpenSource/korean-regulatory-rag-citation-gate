"""ACTIVE/ACTIVATED 정합: the live-house-view readers recognise BOTH the legacy
direct-activate status ('ACTIVE') and the T16 lifecycle terminal ('ACTIVATED').

Before this fix get_active_house_view / the dashboard latest_house_view query only
matched 'ACTIVE', so a lifecycle-activated ('ACTIVATED') house view was invisible
to them. This locks that an ACTIVATED row is returned as the active house view.

Live-schema, transaction rolled back so house_views is never permanently modified.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@pytest.fixture()
def db_config():
    _load_env()
    from apps.api.harness.core.config import load_config

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        pytest.skip(".env not present")
    config = load_config(env_path)
    if not config.database.database_url:
        pytest.skip("DATABASE_URL missing")
    return config


def test_get_active_recognises_activated(db_config):
    from apps.api.harness.repositories.house_views import get_active_house_view

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if emp is None:
                        pytest.skip("no employee seeded")
                    # Control the live set: retire whatever is currently live so a
                    # real seeded ACTIVE row (e.g. an educational house view) cannot
                    # outrank this probe on activated_at. Rolled back with the tx.
                    await conn.execute(_CLEAR_LIVE_SQL)
                    hv_id = uuid.uuid4()
                    # Insert a fresh ACTIVATED row activated "now" so it is the
                    # latest live view; the legacy ACTIVE-only reader would miss it.
                    # version_no is globally UNIQUE; derive the next one. market is
                    # left NULL so idx_house_views_one_activated_per_tuple
                    # (WHERE status='ACTIVATED' AND market IS NOT NULL) does not apply.
                    await conn.execute(
                        "INSERT INTO house_views(id, version_no, period_code, title, "
                        "status_code, summary, created_by_id, activated_at) "
                        "VALUES ($1::uuid, "
                        "(SELECT COALESCE(MAX(version_no), 0) + 1 FROM house_views), "
                        "'TEST_UNIFY', 'ACTIVE/ACTIVATED unify probe', "
                        "'ACTIVATED', 's', $2::uuid, now())",
                        str(hv_id),
                        str(emp["id"]),
                    )
                    active = await get_active_house_view(conn)
                    return None if active is None else str(active["id"]), str(hv_id)
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    returned_id, inserted_id = asyncio.run(_exercise())
    assert returned_id == inserted_id, "get_active_house_view must return the ACTIVATED row"


def test_get_active_excludes_fixture_activated(db_config):
    """A test fixture (period_code GOLDEN_TEST) must NOT be returned as the active
    house view even when it is the most recently activated row — the readers exclude
    fixtures like LIST does, so a QA probe never becomes the dashboard's latest view.
    """
    from apps.api.harness.repositories.house_views import get_active_house_view

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if emp is None:
                        pytest.skip("no employee seeded")
                    # Control the live set: retire whatever is currently live so a
                    # real seeded ACTIVE row cannot outrank this probe's genuine row
                    # on activated_at. Rolled back with the tx.
                    await conn.execute(_CLEAR_LIVE_SQL)
                    genuine_id = uuid.uuid4()
                    fixture_id = uuid.uuid4()
                    insert = (
                        "INSERT INTO house_views(id, version_no, period_code, title, "
                        "status_code, summary, created_by_id, activated_at) VALUES "
                        "($1::uuid, "
                        "(SELECT COALESCE(MAX(version_no), 0) + 1 FROM house_views), "
                        "$2, $3, 'ACTIVATED', 's', $4::uuid, $5::timestamptz)"
                    )
                    # genuine, activated earlier
                    await conn.execute(
                        insert, str(genuine_id), "MVP", "genuine live house view",
                        str(emp["id"]), datetime(2026, 1, 1, tzinfo=UTC),
                    )
                    # fixture, activated LATER — would win on activated_at if not excluded
                    await conn.execute(
                        insert, str(fixture_id), "GOLDEN_TEST", "golden fixture probe",
                        str(emp["id"]), datetime(2026, 12, 31, tzinfo=UTC),
                    )
                    active = await get_active_house_view(conn)
                    active_id = None if active is None else str(active["id"])
                    return active_id, str(genuine_id), str(fixture_id)
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    returned_id, genuine_id, fixture_id = asyncio.run(_exercise())
    assert returned_id != fixture_id, "fixture (GOLDEN_TEST) must be excluded from active view"
    assert returned_id == genuine_id, "genuine ACTIVATED row must win despite being older"


def test_legacy_activate_supersedes_activated(db_config):
    """Legacy /activate must retire a pre-existing T16 'ACTIVATED' row (P2 수렴).

    The legacy direct-activate path asserts a single global live house view, so after
    it activates a DRAFT no 'ACTIVATED' row may remain live — otherwise the readers
    (which match IN ('ACTIVE','ACTIVATED')) would see two live rows. Before this fix
    SUPERSEDE only cleared 'ACTIVE'; it now clears 'ACTIVATED' too.

    Live-schema, transaction rolled back so house_views is never permanently modified.
    """
    from apps.api.harness.repositories.house_views import activate_house_view

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if emp is None:
                        pytest.skip("no employee seeded")
                    # Control the live set: the V082 index forbids even a transient
                    # 2nd non-fixture live row, so retire whatever is live before
                    # inserting this probe's prior-ACTIVATED. Rolled back with the tx.
                    await conn.execute(_CLEAR_LIVE_SQL)
                    activated_id = uuid.uuid4()
                    draft_id = uuid.uuid4()
                    insert = (
                        "INSERT INTO house_views(id, version_no, period_code, title, "
                        "status_code, summary, created_by_id, activated_at) VALUES "
                        "($1::uuid, "
                        "(SELECT COALESCE(MAX(version_no), 0) + 1 FROM house_views), "
                        "$2, $3, $4, 's', $5::uuid, $6::timestamptz)"
                    )
                    # pre-existing T16 ACTIVATED row; market left NULL so
                    # idx_house_views_one_activated_per_tuple does not apply.
                    await conn.execute(
                        insert, str(activated_id), "MVP", "prior activated",
                        "ACTIVATED", str(emp["id"]), datetime(2026, 1, 1, tzinfo=UTC),
                    )
                    # a DRAFT to activate via the legacy direct-activate path
                    await conn.execute(
                        insert, str(draft_id), "MVP", "legacy activate target",
                        "DRAFT", str(emp["id"]), None,
                    )
                    result = await activate_house_view(conn, house_view_id=str(draft_id))
                    prior_status = await conn.fetchval(
                        "SELECT status_code FROM house_views WHERE id = $1::uuid",
                        str(activated_id),
                    )
                    target_status = None if result is None else result["status_code"]
                    return target_status, prior_status
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    target_status, prior_status = asyncio.run(_exercise())
    assert target_status == "ACTIVE", "legacy activate must set the DRAFT to ACTIVE"
    assert prior_status == "SUPERSEDED", (
        "a pre-existing ACTIVATED row must be superseded by legacy activate (P2 수렴)"
    )


# Insert helper: a non-fixture house view at an arbitrary status/tuple. version_no is
# globally UNIQUE so it is derived inline; activated_at is set for live rows only.
_INSERT_HV_SQL = (
    "INSERT INTO house_views(id, version_no, period_code, title, status_code, summary, "
    "created_by_id, market, asset_class, region, activated_at) VALUES "
    "($1::uuid, (SELECT COALESCE(MAX(version_no), 0) + 1 FROM house_views), "
    "$2, $3, $4, 's', $5::uuid, $6, $7, $8, $9::timestamptz)"
)
_CLEAR_LIVE_SQL = (
    "UPDATE house_views SET status_code = 'SUPERSEDED', superseded_at = now() "
    "WHERE status_code IN ('ACTIVE', 'ACTIVATED')"
)


def test_guard_blocks_per_tuple_collision_with_global_active(db_config):
    """ADR-020 guard: a per-tuple ACTIVATED left next to a different-tuple global
    ACTIVE would expose two live views, so activate-lifecycle must refuse and roll
    back (legacy↔lifecycle mutual exclusivity, formalized as a runtime tripwire).

    Live-schema, transaction rolled back so house_views is never permanently modified.
    """
    from apps.api.harness.repositories.house_views import (
        SingleLiveHouseViewViolation,
        activate_lifecycle_house_view,
    )

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if emp is None:
                        pytest.skip("no employee seeded")
                    emp_id = str(emp["id"])
                    # Control the live set: retire whatever is currently live.
                    await conn.execute(_CLEAR_LIVE_SQL)
                    global_active = uuid.uuid4()
                    tuple_reviewed = uuid.uuid4()
                    # A NULL-tuple global ACTIVE (legacy mode in use).
                    await conn.execute(
                        _INSERT_HV_SQL, str(global_active), "MVP", "global active probe",
                        "ACTIVE", emp_id, None, None, None,
                        datetime(2026, 1, 1, tzinfo=UTC),
                    )
                    # A non-NULL-tuple REVIEWED — activating it would create a 2nd live view.
                    await conn.execute(
                        _INSERT_HV_SQL, str(tuple_reviewed), "MVP", "tuple reviewed probe",
                        "REVIEWED", emp_id, "KR", "EQUITY", "APAC", None,
                    )
                    raised = False
                    try:
                        await activate_lifecycle_house_view(
                            conn, house_view_id=str(tuple_reviewed)
                        )
                    except SingleLiveHouseViewViolation:
                        raised = True
                    # After the (rolled-back) activation attempt: REVIEWED stays
                    # REVIEWED, the global ACTIVE survives, exactly one live view.
                    reviewed_status = await conn.fetchval(
                        "SELECT status_code FROM house_views WHERE id = $1::uuid",
                        str(tuple_reviewed),
                    )
                    active_status = await conn.fetchval(
                        "SELECT status_code FROM house_views WHERE id = $1::uuid",
                        str(global_active),
                    )
                    return raised, reviewed_status, active_status
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    raised, reviewed_status, active_status = asyncio.run(_exercise())
    assert raised, "activate-lifecycle must raise when it would leave 2 live views"
    assert reviewed_status == "REVIEWED", "blocked activation must roll back (stays REVIEWED)"
    assert active_status == "ACTIVE", "the global ACTIVE must be untouched by the block"


def test_single_global_live_view_after_legacy_then_lifecycle(db_config):
    """ADR-020 invariant: across a legacy /activate followed by a (same-tuple)
    /activate-lifecycle, the readers expose exactly one global live view (newest
    activation wins) and the predecessor is retired.

    Live-schema, transaction rolled back so house_views is never permanently modified.
    """
    from apps.api.harness.repositories.house_views import (
        COUNT_LIVE_HOUSE_VIEWS_SQL,
        activate_house_view,
        activate_lifecycle_house_view,
        get_active_house_view,
    )

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if emp is None:
                        pytest.skip("no employee seeded")
                    emp_id = str(emp["id"])
                    await conn.execute(_CLEAR_LIVE_SQL)
                    legacy_draft = uuid.uuid4()
                    lifecycle_reviewed = uuid.uuid4()
                    # Both NULL-tuple (global mode) so the lifecycle same-tuple
                    # archive (NULL = NULL) retires the legacy ACTIVE.
                    await conn.execute(
                        _INSERT_HV_SQL, str(legacy_draft), "MVP", "legacy draft probe",
                        "DRAFT", emp_id, None, None, None, None,
                    )
                    await conn.execute(
                        _INSERT_HV_SQL, str(lifecycle_reviewed), "MVP", "lifecycle reviewed probe",
                        "REVIEWED", emp_id, None, None, None, None,
                    )
                    # 1) legacy activate → the DRAFT becomes the single live view.
                    await activate_house_view(conn, house_view_id=str(legacy_draft))
                    after_legacy = await get_active_house_view(conn)
                    count_after_legacy = await conn.fetchval(COUNT_LIVE_HOUSE_VIEWS_SQL)
                    # 2) lifecycle activate (same NULL tuple) → ACTIVATED supersedes it.
                    await activate_lifecycle_house_view(
                        conn, house_view_id=str(lifecycle_reviewed)
                    )
                    after_lifecycle = await get_active_house_view(conn)
                    count_after_lifecycle = await conn.fetchval(COUNT_LIVE_HOUSE_VIEWS_SQL)
                    legacy_status = await conn.fetchval(
                        "SELECT status_code FROM house_views WHERE id = $1::uuid",
                        str(legacy_draft),
                    )
                    return (
                        None if after_legacy is None else str(after_legacy["id"]),
                        int(count_after_legacy),
                        None if after_lifecycle is None else str(after_lifecycle["id"]),
                        int(count_after_lifecycle),
                        legacy_status,
                        str(legacy_draft),
                        str(lifecycle_reviewed),
                    )
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    (
        active_after_legacy,
        count_after_legacy,
        active_after_lifecycle,
        count_after_lifecycle,
        legacy_status,
        legacy_id,
        lifecycle_id,
    ) = asyncio.run(_exercise())
    assert active_after_legacy == legacy_id, "legacy activate must surface the DRAFT as live"
    assert count_after_legacy == 1, "exactly one live view after legacy activate"
    assert active_after_lifecycle == lifecycle_id, "lifecycle activate must surface the ACTIVATED"
    assert count_after_lifecycle == 1, "exactly one live view after the legacy→lifecycle sequence"
    assert legacy_status == "ARCHIVED", "same-tuple lifecycle must archive the legacy ACTIVE"


def test_db_index_rejects_second_non_fixture_live(db_config):
    """ADR-020 F1: the partial UNIQUE index idx_house_views_single_live (V082) forbids
    a SECOND non-fixture live row at the DB level (direct-write backstop), while a
    fixture (RALPH-QA) live row is allowed to coexist (excluded by the predicate).

    Skipped if V082 is not applied to the target DB (the index is migration-gated).
    Live-schema, transaction rolled back so house_views is never permanently modified.
    """
    import asyncpg

    _INS_LIVE = (
        "INSERT INTO house_views(id, version_no, period_code, title, status_code, "
        "summary, created_by_id) VALUES ($1::uuid, "
        "(SELECT COALESCE(MAX(version_no), 0) + 1 FROM house_views), $2, $3, 'ACTIVE', "
        "'s', $4::uuid)"
    )

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                has_index = await conn.fetchval(
                    "SELECT 1 FROM pg_indexes WHERE tablename = 'house_views' "
                    "AND indexname = 'idx_house_views_single_live'"
                )
                if not has_index:
                    pytest.skip("V082 idx_house_views_single_live not applied")
                tr = conn.transaction()
                await tr.start()
                try:
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if emp is None:
                        pytest.skip("no employee seeded")
                    emp_id = str(emp["id"])
                    await conn.execute(_CLEAR_LIVE_SQL)
                    await conn.execute(_INS_LIVE, str(uuid.uuid4()), "MVP", "f1 first live", emp_id)
                    # second non-fixture live row → must trip the unique index
                    violated = False
                    constraint = None
                    try:
                        async with conn.transaction():  # savepoint
                            await conn.execute(
                                _INS_LIVE, str(uuid.uuid4()), "MVP", "f1 second live", emp_id
                            )
                    except asyncpg.exceptions.UniqueViolationError as exc:
                        violated = True
                        constraint = exc.constraint_name
                    # a fixture (RALPH-QA) live row is excluded → must be allowed
                    fixture_ok = False
                    try:
                        async with conn.transaction():  # savepoint
                            await conn.execute(
                                _INS_LIVE, str(uuid.uuid4()), "RALPH-QA", "ralph qa probe", emp_id
                            )
                            fixture_ok = True
                    except asyncpg.exceptions.UniqueViolationError:
                        fixture_ok = False
                    return violated, constraint, fixture_ok
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    violated, constraint, fixture_ok = asyncio.run(_exercise())
    assert violated, "a 2nd non-fixture live row must violate idx_house_views_single_live"
    assert constraint == "idx_house_views_single_live", f"unexpected constraint: {constraint}"
    assert fixture_ok, "a fixture (RALPH-QA) live row must coexist (excluded from the index)"


def test_seed_30_supersede_clears_activated_for_v082_bootstrap():
    """Regression (ADR-020 F1 / V082): the seed_30 house_view supersede MUST clear
    both 'ACTIVE' and 'ACTIVATED'. On a fresh DB, V052's 2099Q4 ACTIVATED dashboard
    fixture survives the migrations as the single non-fixture live row; if the seed
    only superseded 'ACTIVE', inserting its own 2026M05 ACTIVE row would leave two
    non-fixture live rows and trip idx_house_views_single_live, aborting the whole
    one-transaction seed (fresh-environment bootstrap break). This pins the fix so a
    revert to the ACTIVE-only supersede is caught without needing a fresh DB.
    """
    seed = (PROJECT_ROOT / "db" / "fixtures" / "seed_30_workflows.sql").read_text()
    assert (
        "WHERE status_code IN ('ACTIVE', 'ACTIVATED')\n"
        "  AND id <> '77777777-7777-7777-7777-777777777701'::uuid;" in seed
    ), "seed_30 house_view supersede must clear ACTIVE+ACTIVATED (V082 bootstrap)"
    assert (
        "WHERE status_code = 'ACTIVE'\n"
        "  AND id <> '77777777-7777-7777-7777-777777777701'::uuid;" not in seed
    ), "stale ACTIVE-only seed_30 supersede must not return (breaks V082 fresh bootstrap)"


def test_v082_index_predicate_in_sync_with_python_nonfixture():
    """ADR-020 §11 drift guard: the idx_house_views_single_live partial-index WHERE
    in the migration is a FROZEN copy of LIVE_HOUSE_VIEW_STATUS_IN +
    NON_FIXTURE_HOUSE_VIEW_PREDICATE (an index predicate cannot reference the Python
    constants). If the Python predicate changes without a matching migration update,
    the DB index silently diverges from the readers/guard. This asserts they stay in
    sync (whitespace-normalized), so a Python-side change forces a migration update.

    Pure source-to-source (no DB): pg_get_indexdef rewrites IN/NOT IN/LIKE into
    ANY/ALL/!~~ with type casts, so comparing the live index text is unreliable;
    the migration SQL shares the Python constant's formatting and compares cleanly.
    """
    import re

    from apps.api.harness.repositories.house_views import (
        LIVE_HOUSE_VIEW_STATUS_IN,
        NON_FIXTURE_HOUSE_VIEW_PREDICATE,
    )

    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    mig_dir = PROJECT_ROOT / "db" / "migrations"
    # Re-creation-robust: compare against the LATEST migration that CREATEs the
    # index (a future DROP+CREATE migration would supersede V082).
    definers = sorted(
        p
        for p in mig_dir.glob("V*.sql")
        if "CREATE UNIQUE INDEX" in (txt := p.read_text())
        and "idx_house_views_single_live" in txt
    )
    assert definers, "no migration CREATEs idx_house_views_single_live"
    migration_sql = _norm(definers[-1].read_text())

    assert _norm(LIVE_HOUSE_VIEW_STATUS_IN) in migration_sql, (
        f"idx_house_views_single_live live-set predicate drifted from "
        f"LIVE_HOUSE_VIEW_STATUS_IN; update {definers[-1].name} WHERE to match (ADR-020 §11)"
    )
    nonfixture_body = _norm(NON_FIXTURE_HOUSE_VIEW_PREDICATE).strip("() ")
    assert nonfixture_body in migration_sql, (
        f"idx_house_views_single_live fixture-exclusion drifted from "
        f"NON_FIXTURE_HOUSE_VIEW_PREDICATE; update {definers[-1].name} WHERE to match (ADR-020 §11)"
    )
