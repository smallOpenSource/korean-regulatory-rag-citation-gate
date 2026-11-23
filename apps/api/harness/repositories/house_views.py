"""House view repositories."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from asyncpg.exceptions import UniqueViolationError

from apps.api.harness.core.db import execute, fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

# ADR-020 F1: the DB-level backstop index name. A unique violation on it means an
# activation would expose a second non-fixture live house view; the activation
# functions translate it to SingleLiveHouseViewViolation so the router still
# returns 409 (the index fires on the activation UPDATE, before the app guard).
_SINGLE_LIVE_INDEX = "idx_house_views_single_live"

# Shared test-fixture exclusion (bare column names so it embeds in any single
# house_views-table context: LIST, GET_ACTIVE, and the dashboard latest_house_view
# CTE). Hides golden/ralph/QA/synthetic-boundary fixtures from front-office reads.
# Single source of truth — the live-view readers (P2 ACTIVE/ACTIVATED 정합 follow-up)
# now exclude the same fixtures LIST hides, so a QA activation probe never surfaces
# as the dashboard's "latest house view".
NON_FIXTURE_HOUSE_VIEW_PREDICATE = """(
          status_code NOT IN (
              'GOLDEN_TEST', 'GOLDEN', 'RALPH', 'RALPH-QA', 'RALPH_QA',
              'SYNTHETIC_BOUNDARY', 'TEST', 'TEST_FIXTURE',
              'ULTRAQA', 'ULTRA_QA', 'ULTRA-QA', 'QA_DRAFT'
          )
          AND period_code NOT IN (
              'GOLDEN_TEST', 'GOLDEN', 'RALPH', 'RALPH-QA', 'RALPH_QA',
              'SYNTHETIC_BOUNDARY', 'TEST', 'TEST_FIXTURE',
              'ULTRAQA', 'ULTRA_QA', 'ULTRA-QA', 'QA_DRAFT', 'AUDIT'
          )
          AND title NOT LIKE 'AUDIT-%'
          AND title !~* '(golden[ _-]?test|ralph[ _-]?qa|synthetic[ _-]?(boundary|qa)|golden[ _-]?regression|test[ _-]?fixture|qa[ _-]?activation[ _-]?probe|ultra[ _-]?qa)'
          AND COALESCE(summary, '') !~* '(synthetic[ _-]?(boundary|qa)|golden[ _-]?regression|test[ _-]?fixture|qa[ _-]?activation[ _-]?probe|ralph[ _-]?qa|ultra[ _-]?qa)'
      )"""

# Single source of truth for "which statuses count as a *live* house view":
# legacy direct-activate => 'ACTIVE'; T16 lifecycle terminal => 'ACTIVATED'.
# Every live-view reader (GET_ACTIVE, the dashboard latest_house_view CTE) and
# every activation write path (SUPERSEDE, ARCHIVE, the COUNT guard) interpolates
# this one literal so the live-set definition can never drift across SQL strings.
LIVE_HOUSE_VIEW_STATUSES: tuple[str, ...] = ("ACTIVE", "ACTIVATED")
LIVE_HOUSE_VIEW_STATUS_IN = "(" + ", ".join(f"'{s}'" for s in LIVE_HOUSE_VIEW_STATUSES) + ")"


class SingleLiveHouseViewViolation(RuntimeError):
    """An activation would leave more than one *non-fixture* live house view
    visible to the readers.

    Canonical invariant (ADR-020): the readers expose a single global live house
    view. Legacy ``/activate`` (global supersede) and T16 ``/activate-lifecycle``
    (per-(market, asset_class, region) archive) are *mutually-exclusive operating
    models*: the per-tuple machinery can hold several live tuples at once, which
    the global-single readers would collapse to "newest wins" while LIST surfaces
    all of them. This guard formalizes the exclusivity as a runtime tripwire so a
    per-tuple ``ACTIVATED`` can never silently co-exist with a global ``ACTIVE``.
    It is raised inside the activation transaction, so a violation rolls the
    activation back rather than exposing two live views."""


LIST_HOUSE_VIEWS_SQL = f"""
/* sql_id: list_house_views */
SELECT id, version_no, period_code, title, status_code, summary, asset_views_json,
       model_portfolios_json, risks_json, created_by_id, activated_at, superseded_at,
       ai_generated_at, ai_model_name, faithfulness_json, created_at, updated_at
FROM house_views
WHERE ($1::varchar IS NULL OR status_code = $1::varchar)
  AND (
      $4::boolean IS TRUE
      OR {NON_FIXTURE_HOUSE_VIEW_PREDICATE}
  )
ORDER BY version_no DESC, created_at DESC
LIMIT $2 OFFSET $3;
"""

NEXT_HOUSE_VIEW_VERSION_SQL = """
/* sql_id: next_house_view_version */
SELECT COALESCE(MAX(version_no), 0) + 1 AS next_version
FROM house_views;
"""

CREATE_HOUSE_VIEW_SQL = """
/* sql_id: create_house_view */
INSERT INTO house_views(version_no, period_code, title, status_code, summary, asset_views_json,
                        model_portfolios_json, risks_json, created_by_id)
VALUES ($1, $2, $3, 'DRAFT', $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::uuid)
RETURNING id, version_no, period_code, title, status_code, summary, asset_views_json,
          model_portfolios_json, risks_json, created_by_id, activated_at, superseded_at,
          ai_generated_at, ai_model_name, created_at, updated_at;
"""

ACTIVATE_HOUSE_VIEW_SQL = """
/* sql_id: activate_house_view */
UPDATE house_views h
SET status_code = 'ACTIVE', activated_at = now(), updated_at = now()
WHERE h.id = $1::uuid
  AND h.status_code IN ('DRAFT', 'PENDING_REVIEW')
RETURNING h.id, h.version_no, h.period_code, h.title, h.status_code, h.summary,
          h.asset_views_json, h.model_portfolios_json, h.risks_json,
          h.leading_block_json, h.created_by_id,
          h.activated_at, h.superseded_at, h.ai_generated_at, h.ai_model_name,
          h.faithfulness_json, h.created_at, h.updated_at;
"""

GET_ACTIVATABLE_HOUSE_VIEW_SQL = """
/* sql_id: get_activatable_house_view */
SELECT id
FROM house_views
WHERE id = $1::uuid
  AND status_code IN ('DRAFT', 'PENDING_REVIEW')
FOR UPDATE;
"""

SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL = f"""
/* sql_id: supersede_active_house_views */
UPDATE house_views
-- Legacy /activate asserts a single global live house view, so it retires BOTH the
-- legacy 'ACTIVE' predecessor AND any T16 lifecycle 'ACTIVATED' row. Otherwise an
-- ACTIVATED row stays live next to the new ACTIVE and BOTH surface in the live-view
-- readers (dashboard / get_active) — P2 ACTIVE/ACTIVATED 수렴, mirroring the lifecycle's
-- ARCHIVE_ACTIVE_TUPLE which already clears both directions.
-- NOTE: global-single is enforced *procedurally* by this global supersede + the
-- post-activation assert_single_live_house_view guard — NOT by idx_house_views_one_active.
-- That index (V040) is on (market, asset_class, region) WHERE status='ACTIVE'; legacy
-- rows leave the tuple NULL and Postgres treats NULLs as distinct, so the index does
-- not by itself bound the count of NULL-tuple ACTIVE rows (ADR-020).
SET status_code = 'SUPERSEDED', superseded_at = now(), updated_at = now()
WHERE status_code IN {LIVE_HOUSE_VIEW_STATUS_IN}
  AND id <> $1::uuid;
"""

GET_ACTIVE_HOUSE_VIEW_SQL = f"""
/* sql_id: get_active_house_view */
SELECT id, version_no, period_code, title, status_code, summary, asset_views_json,
       model_portfolios_json, risks_json, leading_block_json, created_by_id,
       activated_at, superseded_at,
       ai_generated_at, ai_model_name, faithfulness_json, created_at, updated_at
FROM house_views
-- "live" = legacy direct-activate ('ACTIVE') OR T16 lifecycle terminal ('ACTIVATED');
-- both set activated_at so the most recent activation wins (P2 ACTIVE/ACTIVATED 정합).
-- Test fixtures are excluded (same predicate LIST uses) so a QA activation probe is
-- never returned as the active house view to the dashboard / runner_derived.
WHERE status_code IN {LIVE_HOUSE_VIEW_STATUS_IN}
  AND {NON_FIXTURE_HOUSE_VIEW_PREDICATE}
ORDER BY activated_at DESC
LIMIT 1;
"""

GET_HOUSE_VIEW_SQL = """
/* sql_id: get_house_view */
SELECT id, version_no, period_code, title, status_code, summary, asset_views_json,
       model_portfolios_json, risks_json, leading_block_json, created_by_id,
       activated_at, superseded_at,
       ai_generated_at, ai_model_name, faithfulness_json, created_at, updated_at
FROM house_views
WHERE id = $1::uuid;
"""

COUNT_LIVE_HOUSE_VIEWS_SQL = f"""
/* sql_id: count_live_house_views */
-- Count the rows the live-view readers would surface (same live-set + fixture
-- exclusion as GET_ACTIVE / the dashboard CTE). The canonical invariant is ≤ 1.
SELECT count(*) AS n
FROM house_views
WHERE status_code IN {LIVE_HOUSE_VIEW_STATUS_IN}
  AND {NON_FIXTURE_HOUSE_VIEW_PREDICATE};
"""


async def assert_single_live_house_view(connection: Any) -> None:
    """Enforce the canonical single-global-live-view invariant (ADR-020).

    Counts the non-fixture rows the live-view readers would surface and raises
    :class:`SingleLiveHouseViewViolation` if more than one would be live. Both
    activation paths call this inside their transaction after the write, so a
    violation (e.g. a per-tuple ``ACTIVATED`` left live next to a global
    ``ACTIVE``) rolls the activation back instead of exposing two live views.
    """
    row = await fetch_one(connection, COUNT_LIVE_HOUSE_VIEWS_SQL)
    live_count = int(row["n"]) if row else 0
    if live_count > 1:
        raise SingleLiveHouseViewViolation(
            f"house_view single-live invariant violated: {live_count} non-fixture live views"
        )


async def list_house_views(
    connection: Any,
    *,
    status_code: str | None,
    limit: int,
    offset: int,
    include_test_fixtures: bool = False,
) -> list[dict[str, Any]]:
    """List house views; test fixtures are hidden unless ADMIN/AUDIT_VIEWER opts in."""

    rows = await fetch_all(
        connection,
        LIST_HOUSE_VIEWS_SQL,
        status_code,
        limit,
        offset,
        include_test_fixtures,
    )
    return rows_to_dicts(rows)


async def create_house_view(
    connection: Any,
    *,
    period_code: str,
    title: str,
    summary: str,
    created_by_id: str,
    asset_views: dict[str, Any] | None = None,
    model_portfolios: dict[str, Any] | None = None,
    risks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a draft house view with next version number."""

    version_row = await fetch_one(connection, NEXT_HOUSE_VIEW_VERSION_SQL)
    version_no = int(version_row["next_version"])
    row = await fetch_one(
        connection,
        CREATE_HOUSE_VIEW_SQL,
        version_no,
        period_code,
        title,
        summary,
        json.dumps(asset_views or {}, ensure_ascii=False),
        json.dumps(model_portfolios or {}, ensure_ascii=False),
        json.dumps(risks or {}, ensure_ascii=False),
        created_by_id,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("house view create returned no row")
    return result


async def activate_house_view(connection: Any, *, house_view_id: str) -> dict[str, Any] | None:
    """Activate one house view, superseding previous ACTIVE + ACTIVATED, after target validation."""

    async with connection.transaction():
        target = await fetch_one(connection, GET_ACTIVATABLE_HOUSE_VIEW_SQL, house_view_id)
        if target is None:
            return None
        await execute(connection, SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL, house_view_id)
        try:
            activated = row_to_dict(
                await fetch_one(connection, ACTIVATE_HOUSE_VIEW_SQL, house_view_id)
            )
        except UniqueViolationError as exc:
            # ADR-020 F1 DB backstop fired (a 2nd non-fixture live view) — translate
            # to the domain error so the router still returns 409, not 500.
            if getattr(exc, "constraint_name", None) == _SINGLE_LIVE_INDEX:
                raise SingleLiveHouseViewViolation(
                    "house_view single-live invariant violated (DB index)"
                ) from exc
            raise
        # Canonical single-global-live-view invariant (ADR-020) — app-layer guard;
        # rolls back if the global supersede above somehow left >1 live view.
        await assert_single_live_house_view(connection)
        return activated


async def get_active_house_view(connection: Any) -> dict[str, Any] | None:
    """Read the active house view if one exists."""

    return row_to_dict(await fetch_one(connection, GET_ACTIVE_HOUSE_VIEW_SQL))


async def get_house_view(connection: Any, *, house_view_id: str) -> dict[str, Any] | None:
    """Read one house view by id without mutating activation state."""

    return row_to_dict(await fetch_one(connection, GET_HOUSE_VIEW_SQL, house_view_id))


# ── T16 lifecycle extensions (V035) ──────────────────────────────────────────

ADVANCE_TO_GENERATED_SQL = """
/* sql_id: advance_house_view_to_generated */
UPDATE house_views
SET status_code = 'GENERATED',
    ai_generated_at = $2::timestamptz,
    ai_model_name = $3,
    prompt_tokens = $4::integer,
    completion_tokens = $5::integer,
    inputs_hash = $6,
    asset_views_json = COALESCE($7::jsonb, asset_views_json),
    model_portfolios_json = COALESCE($8::jsonb, model_portfolios_json),
    risks_json = COALESCE($9::jsonb, risks_json),
    summary = COALESCE($10, summary),
    fail_closed_reason_code = $11,
    leading_block_json = COALESCE($12::jsonb, leading_block_json),
    faithfulness_json = COALESCE($13::jsonb, faithfulness_json),
    updated_at = now()
WHERE id = $1::uuid
  AND status_code = 'DRAFT'
RETURNING id, version_no, period_code, title, status_code, summary,
          market, asset_class, region, asset_views_json,
          model_portfolios_json, risks_json, leading_block_json, created_by_id,
          activated_at, superseded_at, ai_generated_at, ai_model_name,
          prompt_tokens, completion_tokens, inputs_hash,
          fail_closed_reason_code, faithfulness_json,
          created_at, updated_at;
"""

ADVANCE_TO_REVIEWED_SQL = """
/* sql_id: advance_house_view_to_reviewed */
UPDATE house_views
SET status_code = 'REVIEWED', updated_at = now()
WHERE id = $1::uuid
  AND status_code = 'GENERATED'
RETURNING id, version_no, period_code, title, status_code, summary,
          market, asset_class, region, asset_views_json,
          model_portfolios_json, risks_json, leading_block_json, created_by_id,
          activated_at, superseded_at, ai_generated_at, ai_model_name,
          faithfulness_json, prompt_tokens, completion_tokens, inputs_hash,
          created_at, updated_at;
"""

ARCHIVE_ACTIVE_TUPLE_SQL = f"""
/* sql_id: archive_active_house_views_for_tuple */
UPDATE house_views
SET status_code = 'ARCHIVED', superseded_at = now(), updated_at = now()
WHERE status_code IN {LIVE_HOUSE_VIEW_STATUS_IN}
  AND id <> $1::uuid
  AND (
        ($2::varchar IS NULL AND market IS NULL)
        OR market = $2::varchar
      )
  AND (
        ($3::varchar IS NULL AND asset_class IS NULL)
        OR asset_class = $3::varchar
      )
  AND (
        ($4::varchar IS NULL AND region IS NULL)
        OR region = $4::varchar
      );
"""

ACTIVATE_REVIEWED_HOUSE_VIEW_SQL = """
/* sql_id: activate_reviewed_house_view */
UPDATE house_views
SET status_code = 'ACTIVATED', activated_at = now(), updated_at = now()
WHERE id = $1::uuid
  AND status_code = 'REVIEWED'
RETURNING id, version_no, period_code, title, status_code, summary,
          market, asset_class, region, asset_views_json,
          model_portfolios_json, risks_json, leading_block_json, created_by_id,
          activated_at, superseded_at, ai_generated_at, ai_model_name,
          faithfulness_json, prompt_tokens, completion_tokens, inputs_hash,
          created_at, updated_at;
"""

GET_HOUSE_VIEW_FOR_LIFECYCLE_SQL = """
/* sql_id: get_house_view_for_lifecycle */
SELECT id, status_code, market, asset_class, region
FROM house_views
WHERE id = $1::uuid
FOR UPDATE;
"""


async def advance_to_generated(
    connection: Any,
    *,
    house_view_id: str,
    generated_at: datetime,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    inputs_hash: str,
    content: dict[str, Any],
    fail_closed_reason_code: str | None = None,
    faithfulness: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Transition DRAFT → GENERATED with Azure generation metadata (T16).

    ``fail_closed_reason_code`` (Wave-Audit-Defect-Fix A5 / CR-6 — V055): when the
    upstream generator reports leakage / Content-Safety / parse failure, the
    closed-set ADR-005 reason code is persisted on the row so safety branches
    leave audit evidence (NULL on success).

    ``faithfulness`` (P2-3, V081): the deterministic faithfulness assessment of the
    generated prose against the market-data input, persisted so GET /house-views
    can expose the same grounding signal the dispatchers carry on ai_outputs.
    """
    summary = str(content.get("summary") or "")
    asset_views = json.dumps(content.get("asset_views") or {}, ensure_ascii=False)
    model_portfolios = json.dumps(content.get("model_portfolios") or {}, ensure_ascii=False)
    risks = json.dumps(content.get("risks") or {}, ensure_ascii=False)
    leading_block = json.dumps(content.get("leading_block") or {}, ensure_ascii=False)
    faithfulness_payload = (
        json.dumps(faithfulness, ensure_ascii=False) if faithfulness else None
    )

    row = await fetch_one(
        connection,
        ADVANCE_TO_GENERATED_SQL,
        house_view_id,
        generated_at,
        model_name,
        prompt_tokens,
        completion_tokens,
        inputs_hash,
        asset_views,
        model_portfolios,
        risks,
        summary or None,
        fail_closed_reason_code,
        leading_block,
        faithfulness_payload,
    )
    return row_to_dict(row)


async def advance_to_reviewed(
    connection: Any, *, house_view_id: str
) -> dict[str, Any] | None:
    """Transition GENERATED → REVIEWED (T16 reviewer approval)."""
    return row_to_dict(
        await fetch_one(connection, ADVANCE_TO_REVIEWED_SQL, house_view_id)
    )


async def activate_lifecycle_house_view(
    connection: Any, *, house_view_id: str
) -> dict[str, Any] | None:
    """REVIEWED → ACTIVATED; archive previous ACTIVATED for same (market, asset_class, region)."""
    async with connection.transaction():
        lock_row = await fetch_one(
            connection, GET_HOUSE_VIEW_FOR_LIFECYCLE_SQL, house_view_id
        )
        if lock_row is None or lock_row["status_code"] != "REVIEWED":
            return None
        # Archive previous ACTIVATED rows for the same market tuple
        await execute(
            connection,
            ARCHIVE_ACTIVE_TUPLE_SQL,
            house_view_id,
            lock_row["market"],
            lock_row["asset_class"],
            lock_row["region"],
        )
        try:
            activated = row_to_dict(
                await fetch_one(
                    connection, ACTIVATE_REVIEWED_HOUSE_VIEW_SQL, house_view_id
                )
            )
        except UniqueViolationError as exc:
            # ADR-020 F1 DB backstop: ACTIVATE_REVIEWED creating a 2nd non-fixture
            # live view trips idx_house_views_single_live BEFORE the app guard's
            # COUNT runs. Translate so the router still returns 409, not 500.
            if getattr(exc, "constraint_name", None) == _SINGLE_LIVE_INDEX:
                raise SingleLiveHouseViewViolation(
                    "house_view single-live invariant violated (DB index)"
                ) from exc
            raise
        # Canonical single-global-live-view invariant (ADR-020): the per-tuple
        # archive above only clears the SAME (market, asset_class, region); if a
        # different-tuple live view (e.g. a global NULL-tuple ACTIVE) survives, the
        # readers would expose two live views, so refuse and roll back. This app-layer
        # guard is the SoT; the F1 index above is the DB backstop for direct writes.
        await assert_single_live_house_view(connection)
        return activated
