"""Service Viability Audit v1 — Axis 3 data integrity (5 SELECT).

Reads txid pairs produced by ``audit_v1_workflow_e2e.py`` (worker-1 commit a30968b)
and emits 5 JSON artifacts under ``audit-out/service-viability-v1/axis-3/``:

(1) data/action_code_distribution.json — cycle-window action_code counts +
    canonical-subset diff against ``audit_action_codes`` lookup table (V008 SoT).
(2) data/4eye_self_join.json — ``email_drafts.employee_id = approved_by_id AND
    status_code = 'APPROVED'`` self-join (V008:81 + V034:17). Hit > 0 is captured
    as F3 evidence (4-eye marketing-only).
(3) data/synthetic_prefix.json — ``customers.customer_no NOT LIKE 'SYN-%'`` direct
    + dispute_cases indirect via customer_id join (V037:5-8 CHECK).
(4) data/append_only.json — per-txid-pair audit_logs row count (4 pairs from
    txid_pairs.json), summed; UPDATE/DELETE counter snapshot
    (``pg_stat_user_tables`` on audit_logs).
(5) data/v067_v068_counts.json — baseline (worker-1 step 0) vs post-cycle counts
    of OPEN/GENERATED/DRAFT for dispute_cases / kyc_edd_triggers / house_views /
    email_drafts; +12 row delta evidence preserved.

All 5 statements are SELECT only — V008/V019 RAISE EXCEPTION trigger forbids
UPDATE/DELETE/TRUNCATE on audit_logs (R-Arch-4).

Reference: ``.omc/plans/ralplan-wmah-service-viability-audit-v1.2.md`` §3.3 +
§4 Axis 3 PASS criteria.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "audit-out" / "service-viability-v1" / "axis-3" / "data"
TXID_PATH = REPO_ROOT / "audit-out" / "service-viability-v1" / "axis-2" / "txid_pairs.json"
STEP0_BASELINE_PATH = REPO_ROOT / "audit-out" / "service-viability-v1" / "step0-ops-pause.md"

# .env를 먼저 로드해 DATABASE_URL을 SoT로 확보한다(하드코딩 DSN 금지).
load_dotenv(REPO_ROOT / ".env")

# AUDIT_V1_DSN override는 유지하되, 기본값은 하드코딩 literal이 아니라 .env의
# DATABASE_URL을 사용한다. 비밀번호 %21 등 URL-encoding은 asyncpg가 자동 디코딩한다.
DSN = os.environ.get("AUDIT_V1_DSN") or os.environ.get("DATABASE_URL")

# Cycle start = V068 commit b9a372e timestamp (2026-05-24 16:39:44 +0900).
# Anything inserted before this is V067/pre-cycle.  KST → UTC = 07:39:44Z.
CYCLE_START_ISO = "2026-05-24T07:39:44+00:00"
CYCLE_START_DT = datetime.fromisoformat(CYCLE_START_ISO)

# Cycle actors per plan §3.0 / F3 — see V067:48/81/125/162 + axis-2 summary.actor_ids.
PB1_ID = "22222222-2222-2222-2222-222222222201"
WM1_ID = "22222222-2222-2222-2222-222222222202"
ADMIN_ID = "22222222-2222-2222-2222-222222222203"
CYCLE_ACTORS = [PB1_ID, WM1_ID, ADMIN_ID]

# worker-1 step 0 baseline (V068 apply 직전, V068 헤더 8-16 lines 실측 박제):
#   dispute_cases OPEN = 0
#   kyc_edd_triggers OPEN = 0
#   house_views GENERATED = 63
#   email_drafts DRAFT = 98
BASELINE_PRE_V068 = {
    "dispute_OPEN": 0,
    "kyc_OPEN": 0,
    "house_GENERATED": 63,
    "email_DRAFT": 98,
}

# V068 delta per migration body (3+3+3+3 = +12).
V068_DELTA = {
    "dispute_OPEN": 3,
    "kyc_OPEN": 3,
    "house_GENERATED": 3,
    "email_DRAFT": 3,
}


def _write_json(name: str, payload: dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return path


async def select_1_action_code_distribution(conn: asyncpg.Connection) -> dict[str, Any]:
    """SELECT (1): action_code distribution within cycle window vs canonical set.

    Canonical set = ``audit_action_codes`` lookup table (V008 + V022 + V029 + V033
    + V034 + V058/059/060 expansions).  Any observed action_code outside this set
    is FK violation impossible (FK constraint V008:36), but we re-assert at the
    application layer to surface drift.
    """
    canonical_rows = await conn.fetch(
        "SELECT action_code FROM audit_action_codes ORDER BY action_code"
    )
    canonical = {r["action_code"] for r in canonical_rows}

    dist_rows = await conn.fetch(
        """
        SELECT action_code, count(*)::bigint AS cnt
        FROM audit_logs
        WHERE created_at >= $1::timestamptz
          AND actor_id = ANY($2::uuid[])
        GROUP BY action_code
        ORDER BY action_code
        """,
        CYCLE_START_DT,
        CYCLE_ACTORS,
    )
    observed = {r["action_code"]: int(r["cnt"]) for r in dist_rows}

    unknown = sorted(set(observed) - canonical)
    pass_flag = len(unknown) == 0

    payload = {
        "select_index": 1,
        "select_name": "action_code_distribution",
        "cycle_start_iso": CYCLE_START_ISO,
        "actor_filter": CYCLE_ACTORS,
        "canonical_count": len(canonical),
        "observed_count": len(observed),
        "observed_total_rows": sum(observed.values()),
        "observed": observed,
        "unknown_action_codes": unknown,
        "binary_acceptance": "PASS" if pass_flag else "FAIL",
        "evidence_refs": [
            "db/migrations/V008__audit_email_ai.sql:9-30 (FK source of truth)",
            "docs/observability/OBS-02_audit_action_codes.md:1-130 (Korean human doc)",
        ],
    }
    return payload


async def select_2_four_eye_self_join(conn: asyncpg.Connection) -> dict[str, Any]:
    """SELECT (2): email_drafts self-approve self-join (4-eye violation surface).

    F3 finding: 4-eye rule is enforced only when ``marketing_classified = TRUE``.
    Hit > 0 on non-marketing drafts is therefore F3 evidence (raw count + sample).
    """
    rows = await conn.fetch(
        """
        SELECT id, employee_id, approved_by_id, status_code, marketing_classified,
               submitted_at, approved_at
        FROM email_drafts
        WHERE employee_id = approved_by_id
          AND status_code = 'APPROVED'
        ORDER BY approved_at DESC NULLS LAST
        LIMIT 20
        """
    )
    total = await conn.fetchval(
        """
        SELECT count(*) FROM email_drafts
        WHERE employee_id = approved_by_id AND status_code = 'APPROVED'
        """
    )
    total_marketing = await conn.fetchval(
        """
        SELECT count(*) FROM email_drafts
        WHERE employee_id = approved_by_id
          AND status_code = 'APPROVED'
          AND marketing_classified = TRUE
        """
    )
    total_non_marketing = (total or 0) - (total_marketing or 0)

    sample = [
        {
            "id": str(r["id"]),
            "employee_id": str(r["employee_id"]),
            "approved_by_id": str(r["approved_by_id"]),
            "status_code": r["status_code"],
            "marketing_classified": r["marketing_classified"],
            "submitted_at": r["submitted_at"],
            "approved_at": r["approved_at"],
        }
        for r in rows
    ]

    # binary acceptance per teammate brief: "report measured (F3 evidence 가능)"
    # — 0 = full PASS; >0 with marketing_classified=False rows = F3 confirmed.
    if total == 0:
        verdict = "PASS"
    elif total_non_marketing > 0:
        verdict = "F3_EVIDENCE_NON_MARKETING_SELF_APPROVE"
    else:
        verdict = "MARKETING_ONLY_SELF_APPROVE_REVIEW"

    payload = {
        "select_index": 2,
        "select_name": "four_eye_self_join",
        "schema_columns_verified": {
            "employee_id": "V008:81 (email_drafts.employee_id author column)",
            "approved_by_id": "V034:17 (email_drafts.approved_by_id approver column)",
            "status_code": "V034:7-8 ('APPROVED' enum member)",
            "marketing_classified": "V034:31 (BOOLEAN NOT NULL DEFAULT false)",
        },
        "total_hits": int(total or 0),
        "marketing_hits": int(total_marketing or 0),
        "non_marketing_hits": int(total_non_marketing or 0),
        "sample_rows": sample,
        "binary_acceptance": verdict,
        "f3_note": (
            "F3 (handoff): 4-eye 강제는 marketing_classified=True 만 적용 — 비-marketing "
            "draft에서 self-approve 발생 가능."
        ),
    }
    return payload


async def select_3_synthetic_prefix(conn: asyncpg.Connection) -> dict[str, Any]:
    """SELECT (3): customers.customer_no SYN- prefix CHECK guardrail."""
    direct = await conn.fetchval(
        "SELECT count(*) FROM customers WHERE customer_no NOT LIKE 'SYN-%'"
    )
    indirect_disputes = await conn.fetchval(
        """
        SELECT count(*) FROM dispute_cases dc
        JOIN customers c ON c.id = dc.customer_id
        WHERE c.customer_no NOT LIKE 'SYN-%'
        """
    )

    direct_count = int(direct or 0)
    indirect_count = int(indirect_disputes or 0)
    pass_flag = direct_count == 0 and indirect_count == 0

    payload = {
        "select_index": 3,
        "select_name": "synthetic_prefix",
        "evidence_refs": [
            "db/migrations/V037__synthetic_customer_no_check.sql:5-8 (CHECK on customers.customer_no only)",
        ],
        "non_synthetic_customers_direct": direct_count,
        "non_synthetic_dispute_cases_indirect": indirect_count,
        "binary_acceptance": "PASS" if pass_flag else "FAIL",
    }
    return payload


async def select_4_append_only(conn: asyncpg.Connection) -> dict[str, Any]:
    """SELECT (4): per-txid-pair audit_logs INSERT count + mutation counter snapshot.

    Per F4 (handoff): script reads axis-2/txid_pairs.json (4 pairs: HP1, NP1, NP2,
    NP3) and runs the count SQL per pair, then sums.  pg_stat_user_tables provides
    the DB-wide UPDATE/DELETE counter — if RAISE EXCEPTION trigger held during
    cycle, n_tup_upd / n_tup_del deltas should be 0 (or unchanged vs pre-cycle).
    """
    txid_pairs = json.loads(TXID_PATH.read_text())

    per_pair: list[dict[str, Any]] = []
    total_inserts = 0
    for scenario, pair in txid_pairs.items():
        start = int(pair["start"])
        end = int(pair["end"])
        cnt = await conn.fetchval(
            """
            SELECT count(*) FROM audit_logs
            WHERE xmin::text::bigint BETWEEN $1 AND $2
              AND actor_id = ANY($3::uuid[])
            """,
            start,
            end,
            CYCLE_ACTORS,
        )
        cnt_int = int(cnt or 0)
        total_inserts += cnt_int
        per_pair.append(
            {
                "scenario": scenario,
                "txid_start": start,
                "txid_end": end,
                "audit_inserts_in_range": cnt_int,
            }
        )

    mutation_stat = await conn.fetchrow(
        """
        SELECT n_tup_ins, n_tup_upd, n_tup_del
        FROM pg_stat_user_tables
        WHERE relname = 'audit_logs'
        """
    )
    mutation_summary = dict(mutation_stat) if mutation_stat else {}

    # binary acceptance: ≥ 9 합산 (teammate brief expected total) + n_tup_upd / n_tup_del
    # delta cannot be measured here w/o pre-snapshot but counter values are recorded.
    sum_ok = total_inserts >= 9
    payload = {
        "select_index": 4,
        "select_name": "append_only",
        "txid_pairs_source": str(TXID_PATH.relative_to(REPO_ROOT)),
        "per_pair": per_pair,
        "txid_pair_count": len(per_pair),
        "total_inserts_sum": total_inserts,
        "expected_minimum_sum": 9,
        "pg_stat_user_tables_audit_logs": mutation_summary,
        "trigger_evidence_refs": [
            "db/migrations/V008__audit_email_ai.sql:52-75 (prevent_audit_log_update_delete + BEFORE UPDATE/DELETE triggers)",
        ],
        "binary_acceptance": "PASS" if sum_ok else "FAIL",
    }
    return payload


async def select_5_v067_v068_counts(conn: asyncpg.Connection) -> dict[str, Any]:
    """SELECT (5): post-cycle counts for OPEN/GENERATED/DRAFT 4 tables.

    Compares against worker-1 step 0 baseline (BASELINE_PRE_V068) + V068 delta
    (+3 per table = +12 total).  Some V068-seeded rows may have transitioned
    state during HP1/NP1/NP2/NP3 cycle execution — measured value recorded
    verbatim, delta vs baseline computed but not asserted as binary PASS/FAIL
    when cycle transitions confound the comparison.
    """
    counts_row = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM dispute_cases WHERE status = 'OPEN')              AS dispute_open,
            (SELECT count(*) FROM kyc_edd_triggers WHERE status = 'OPEN')           AS kyc_open,
            (SELECT count(*) FROM house_views WHERE status_code = 'GENERATED')      AS house_generated,
            (SELECT count(*) FROM email_drafts WHERE status_code = 'DRAFT')         AS email_draft
        """
    )
    post = {
        "dispute_OPEN": int(counts_row["dispute_open"]),
        "kyc_OPEN": int(counts_row["kyc_open"]),
        "house_GENERATED": int(counts_row["house_generated"]),
        "email_DRAFT": int(counts_row["email_draft"]),
    }

    delta_vs_baseline = {
        k: post[k] - BASELINE_PRE_V068[k] for k in BASELINE_PRE_V068
    }
    delta_vs_baseline_plus_v068 = {
        k: post[k] - (BASELINE_PRE_V068[k] + V068_DELTA[k]) for k in BASELINE_PRE_V068
    }

    # V068 SYN- id explicit re-check (3+3+3+3 must persist as long as not deleted —
    # V068 INSERT ON CONFLICT (id) DO NOTHING is non-destructive).
    v068_id_persistence = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM dispute_cases WHERE id IN (
                '88888888-8888-8888-8888-880000001205',
                '88888888-8888-8888-8888-880000001206',
                '88888888-8888-8888-8888-880000001207'))                            AS dispute_v068_present,
            (SELECT count(*) FROM kyc_edd_triggers WHERE id IN (
                '88888888-8888-8888-8888-880000000606',
                '88888888-8888-8888-8888-880000000607',
                '88888888-8888-8888-8888-880000000608'))                            AS kyc_v068_present,
            (SELECT count(*) FROM house_views WHERE id IN (
                '88888888-8888-8888-8888-880000000901',
                '88888888-8888-8888-8888-880000000902',
                '88888888-8888-8888-8888-880000000903'))                            AS house_v068_present,
            (SELECT count(*) FROM email_drafts WHERE id IN (
                '88888888-8888-8888-8888-880000000e01',
                '88888888-8888-8888-8888-880000000e02',
                '88888888-8888-8888-8888-880000000e03'))                            AS email_v068_present
        """
    )
    v068_persistence = {
        "dispute_v068_rows_present": int(v068_id_persistence["dispute_v068_present"]),
        "kyc_v068_rows_present": int(v068_id_persistence["kyc_v068_present"]),
        "house_v068_rows_present": int(v068_id_persistence["house_v068_present"]),
        "email_v068_rows_present": int(v068_id_persistence["email_v068_present"]),
    }
    v068_persistence_total = sum(v068_persistence.values())

    # Same V068 ids but filtered by their seeded state — surfaces cycle-driven
    # transitions (e.g. NP1 may have left an email_draft in non-DRAFT state).
    v068_state_check = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM dispute_cases WHERE status = 'OPEN' AND id IN (
                '88888888-8888-8888-8888-880000001205',
                '88888888-8888-8888-8888-880000001206',
                '88888888-8888-8888-8888-880000001207'))                            AS dispute_v068_still_open,
            (SELECT count(*) FROM kyc_edd_triggers WHERE status = 'OPEN' AND id IN (
                '88888888-8888-8888-8888-880000000606',
                '88888888-8888-8888-8888-880000000607',
                '88888888-8888-8888-8888-880000000608'))                            AS kyc_v068_still_open,
            (SELECT count(*) FROM house_views WHERE status_code = 'GENERATED' AND id IN (
                '88888888-8888-8888-8888-880000000901',
                '88888888-8888-8888-8888-880000000902',
                '88888888-8888-8888-8888-880000000903'))                            AS house_v068_still_generated,
            (SELECT count(*) FROM email_drafts WHERE status_code = 'DRAFT' AND id IN (
                '88888888-8888-8888-8888-880000000e01',
                '88888888-8888-8888-8888-880000000e02',
                '88888888-8888-8888-8888-880000000e03'))                            AS email_v068_still_draft
        """
    )
    v068_state = {k: int(v) for k, v in v068_state_check.items()}

    payload = {
        "select_index": 5,
        "select_name": "v067_v068_counts",
        "baseline_pre_v068": BASELINE_PRE_V068,
        "v068_delta_per_table": V068_DELTA,
        "v068_delta_total": sum(V068_DELTA.values()),
        "post_cycle_measured": post,
        "delta_vs_baseline": delta_vs_baseline,
        "delta_vs_baseline_plus_v068": delta_vs_baseline_plus_v068,
        "v068_seeded_row_persistence_by_id": v068_persistence,
        "v068_seeded_row_persistence_total": v068_persistence_total,
        "v068_seeded_row_state_retained": v068_state,
        "binary_acceptance": (
            "PASS" if v068_persistence_total == 12 else "FAIL"
        ),
        "note": (
            "post_cycle_measured는 HP1+NP1+NP2+NP3 시나리오 transition을 포함하므로 "
            "baseline+V068 단순 합산과 일치하지 않을 수 있음 (cycle 동안 일부 row가 "
            "DRAFT→PENDING_APPROVAL→APPROVED 등으로 전이). V068 +12 row delta 확인은 "
            "v068_seeded_row_persistence_total (12 expected) 으로 수행."
        ),
    }
    return payload


async def main() -> int:
    if not DSN:
        print(
            "ERROR: DSN이 비어 있습니다. AUDIT_V1_DSN 또는 .env의 DATABASE_URL을 설정하세요.",
            file=sys.stderr,
        )
        return 2
    started_at = datetime.now(timezone.utc).isoformat()
    conn = await asyncpg.connect(DSN)
    try:
        s1 = await select_1_action_code_distribution(conn)
        s2 = await select_2_four_eye_self_join(conn)
        s3 = await select_3_synthetic_prefix(conn)
        s4 = await select_4_append_only(conn)
        s5 = await select_5_v067_v068_counts(conn)
    finally:
        await conn.close()
    finished_at = datetime.now(timezone.utc).isoformat()

    paths = [
        _write_json("action_code_distribution.json", s1),
        _write_json("4eye_self_join.json", s2),
        _write_json("synthetic_prefix.json", s3),
        _write_json("append_only.json", s4),
        _write_json("v067_v068_counts.json", s5),
    ]

    summary = {
        "cycle": "service-viability-v1",
        "axis": "axis-3",
        "owner": "worker-2",
        "started_at": started_at,
        "finished_at": finished_at,
        "selects": {
            "1_action_code_distribution": s1["binary_acceptance"],
            "2_four_eye_self_join": s2["binary_acceptance"],
            "3_synthetic_prefix": s3["binary_acceptance"],
            "4_append_only": s4["binary_acceptance"],
            "5_v067_v068_counts": s5["binary_acceptance"],
        },
        "artifact_paths": [str(p.relative_to(REPO_ROOT)) for p in paths],
        "constraints": [
            "asyncpg direct (no REST cache / RLS bypass)",
            "SELECT only — UPDATE/DELETE/TRUNCATE 부재 (audit_logs append-only)",
            "actor_id IN (PB1, WM1, ADMIN) filter — F3 cron noise 차단",
        ],
        "notes": [
            "S2 결과가 >0 이면 F3 (4-eye marketing-only) 정량 evidence — non_marketing_hits 확인.",
            "S5 post_cycle_measured는 HP1+NP* transition 포함 — V068 +12 확인은 v068_seeded_row_persistence_total 사용.",
        ],
    }
    summary_path = ARTIFACT_DIR.parent / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
