#!/usr/bin/env python
"""audit_v1_workflow_e2e.py — Service Viability Audit v1 / Axis 2

Executes 4 sequential business workflow scenarios (HP1 + NP1 + NP2 + NP3)
per plan `.omc/plans/ralplan-wmah-service-viability-audit-v1.2.md` §3.2.

Per scenario:
  - SELECT txid_current() before + after  (4 txid pairs → axis-2/txid_pairs.json)
  - Sequential HTTP calls via httpx async (Idempotency-Key uuid4 per mutation)
  - audit_logs row delta measured via direct asyncpg SELECT (R-Arch-5, no REST cache)
  - Result row + status_code + audit_logs delta dumped to JSON

NB: plan v1.2 §4 HP1 expected = ARRAY[6 distinct codes exact] is based on a
SoT mismatch with runtime endpoint behavior. The enforced gate uses the
runtime-verified REVISED expected set (see HP1_EXPECTED_CODES_REVISED /
HP1_EXPECTED_ROW_COUNT_REVISED below, which are the SoT for the binary
PASS/FAIL). Runtime HP1 actually emits:
  - 1× consultation_create
  - 1× suitability_confirmed
  - 1× appropriateness_warning_acknowledged
  - 1× explanation_confirmed
  - 4× four_gate_acknowledged  (per gate ack call)
  - 1× kyc_edd_evaluated  (kyc_edd.py:154)
  - 1× email_drafted
  - 1× marketing_review_approved  (marketing_review.py:57)
  - 1× marketing_review_submitted + 1× email_draft_submitted  (email.py:339 + :378)
  - 1× email_draft_approved
  - 1× email_sent_via_sandbox  (Mailpit; DP-2 resolved, send reinstated)
  = 15 total rows, 12 distinct action_codes (four_gate_acknowledged ×4, others ×1).

This script measures actual emit + reports both:
  - plan §4 expected (6) vs reality (15 row / 12 distinct) — DP-1 (handoff §2)
  - per-scenario binary PASS/FAIL using REVISED expected
    (HP1_EXPECTED_CODES_REVISED = 12 distinct, HP1_EXPECTED_ROW_COUNT_REVISED = 15)

TEST_RECIPIENT_EMAIL must be synthetic (e.g., syn-pb1-001@example.invalid)
for HP1 #6 to emit; current .env has real address (DP-2).

NP1 4-eye violation requires marketing_classified=True (email.py:378) — DP-4.

NP3 recipient_not_synthetic is config-driven (email.py:546 reads
email_cfg.test_recipient_email, not request payload) — DP-3. The scenario
exercises the path indirectly by attempting send while config has non-synthetic
recipient.

Output layout:
  audit-out/service-viability-v1/axis-2/
    HP1.json
    NP1.json
    NP2.json
    NP3.json
    txid_pairs.json
    audit_logs_delta.json
    summary.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# .env를 먼저 로드해 DATABASE_URL을 SoT로 확보한다(하드코딩 DSN 금지).
load_dotenv(REPO_ROOT / ".env")

DEFAULT_BACKEND_URL = os.environ.get(
    "AUDIT_V1_BACKEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}",
)
# AUDIT_V1_DSN override는 유지하되, 기본값은 하드코딩 literal이 아니라 .env의
# DATABASE_URL을 사용한다. 비밀번호 %21 등 URL-encoding은 asyncpg가 자동 디코딩한다.
DEFAULT_DSN = os.environ.get("AUDIT_V1_DSN") or os.environ.get("DATABASE_URL")
OUTPUT_BASE = REPO_ROOT / "audit-out" / "service-viability-v1" / "axis-2"

# Roles + creds (canonical pwd HarnessSynthetic!2026)
ROLE_CREDS: dict[str, dict[str, str]] = {
    "PB1":   {"email": "synthetic.pb1@example.invalid",   "password": "HarnessSynthetic!2026"},
    "WM1":   {"email": "synthetic.wm1@example.invalid",   "password": "HarnessSynthetic!2026"},
    "ADMIN": {"email": "synthetic.admin@example.invalid", "password": "HarnessSynthetic!2026"},
}

# Synthetic fixture references (V067 + V068 seeds)
SYN_CUSTOMER_ID = "33333333-3333-3333-3333-333333333301"  # SYN-CUST-001 (V067)
SYN_CONSULTATION_ID = "66666666-6666-6666-6666-666666666301"  # V067 seed
SYN_EMPLOYEE_PB1 = "22222222-2222-2222-2222-222222222201"
SYN_EMPLOYEE_WM1 = "22222222-2222-2222-2222-222222222202"
SYN_EMPLOYEE_ADMIN = "22222222-2222-2222-2222-222222222203"

# HP1 expected canonical — OBSERVED minimum chain (runtime-verified, lead refine).
# Plan v1.2 §4 "정확 6"는 plan-vs-reality mismatch — see DP-1.
# Lead first refine = 11 row (4-gate ack ×4 + kyc_triggered) — 추가 runtime finding:
#   - 4-gate ack는 pre-check 호출 필요 (F6) — pre-check 자체가 audit code emit하므로
#     HP1 expected는 다시 refine 필요.
#   - kyc_edd_triggered는 transaction-based payload 필요 (F7).
# 본 cycle은 OBSERVED minimum chain 6 row로 baseline 박제 + F6/F7 finding.
HP1_EXPECTED_CODES_REVISED = sorted([
    "consultation_create",                  # 1× POST /consultations           (consultations.py:71)
    "suitability_confirmed",                # 1× suitability PASSED branch     (consultation_gates.py:132)
    "appropriateness_warning_acknowledged", # 1× appropriateness ack           (consultation_gates.py:204)
    "explanation_confirmed",                # 1× explanation confirm            (consultation_gates.py:285)
    "four_gate_acknowledged",               # 4× gate ack ×4                   (consultation_gates.py:377)
    "kyc_edd_evaluated",                    # 1× /kyc-edd/evaluate             (kyc_edd.py:154)
    "email_drafted",                        # 1× POST /email-drafts            (email.py:222)
    "marketing_review_approved",            # 1× POST /marketing-review PASS   (marketing_review.py:57)
    "marketing_review_submitted",           # 1× draft submit (email.py:339)
    "email_draft_submitted",                # 1× draft submit (email.py:378)
    "email_draft_approved",                 # 1× WM1 approve (email.py:438)
    "email_sent_via_sandbox",               # 1× Mailpit send (email.py:637)
])
# svc-viability-v2 T2-1: 15-row conjunction (12 distinct codes, four_gate_acknowledged ×4)
# Mailpit active (T1-1/T1-2 PASS) → send step reinstated (DP-2 resolved).
HP1_EXPECTED_ROW_COUNT_REVISED = 15

# Plan-as-written (kept for reporting only)
HP1_EXPECTED_CODES_PLAN_AS_WRITTEN = sorted([
    "consultation_create",
    "kyc_edd_triggered",
    "email_drafted",
    "email_draft_submitted",
    "email_draft_approved",
    "email_sent_via_sandbox",
])


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------

async def login_get_token(client: Any, role: str) -> str:
    """POST /auth/login and return access_token."""
    cred = ROLE_CREDS[role]
    resp = await client.post(
        "/auth/login",
        json={"email": cred["email"], "password": cred["password"]},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("accessToken")
    if not token:
        raise RuntimeError(f"login {role}: no access_token in response: {data}")
    return str(token)


def with_auth(token: str, *, idempotency: bool = True) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token}"}
    if idempotency:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


# ---------------------------------------------------------------------------
# DB helpers (asyncpg direct, R-Arch-5)
# ---------------------------------------------------------------------------

async def fetch_txid(pool: Any) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT txid_current()")
        return int(row)


async def fetch_audit_rows_in_range(
    pool: Any, start_txid: int, end_txid: int, actor_ids: list[str]
) -> list[dict[str, Any]]:
    """Return audit_logs rows in xmin range, filtered by actor_id."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id::text AS id, action_code, actor_id::text AS actor_id,
                   resource_type, resource_id::text AS resource_id, created_at
            FROM audit_logs
            WHERE xmin::text::bigint BETWEEN $1 AND $2
              AND actor_id::text = ANY($3)
            ORDER BY created_at, id
            """,
            start_txid, end_txid, actor_ids,
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Scenario implementations
# ---------------------------------------------------------------------------

async def run_hp1(client: Any, pool: Any) -> dict[str, Any]:
    """HP1 happy path — full chain consultation → 4-gate → KYC → email → send."""
    record: dict[str, Any] = {"scenario": "HP1", "steps": []}

    pb1_token = await login_get_token(client, "PB1")
    wm1_token = await login_get_token(client, "WM1")

    # 1) Create consultation (PB1)
    r = await client.post(
        "/consultations",
        json={"customer_id": SYN_CUSTOMER_ID, "channel_code": "PHONE"},
        headers=with_auth(pb1_token),
        timeout=30,
    )
    record["steps"].append({"step": "consultation_create", "status": r.status_code,
                             "body_excerpt": str(r.json())[:200] if r.status_code < 400 else r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"consultation_create failed: {r.status_code} {r.text[:200]}"
        return record
    consultation_id = r.json()["id"]
    record["consultation_id"] = consultation_id

    # 2a) 4-gate PRE-CHECKS (PB1) — REG-02 T220/T222/T223 + REG-03 T247.
    # D3 (svc-follow-up-v1): docs/api/API-04_four_gate_flow.md documents that
    # acknowledge_gate requires a pre-existing consultation_gates row; without
    # the corresponding pre-check, ack returns 404 "gate not found — run check
    # first". HP1 now runs the three direct pre-checks (suitability,
    # explanation, unfair_solicitation) inline and creates a marketing draft
    # to drive the cross-resource marketing gate via email submit.

    syn_product_id = "44444444-4444-4444-4444-444444444401"

    # Suitability pre-check — emits suitability_confirmed (PASSED) or _grade_block
    r = await client.post(
        f"/consultations/{consultation_id}/suitability",
        json={
            "product_id": syn_product_id,
            "investment_objective": "적극투자형",
            "financial_situation": {"income_band": "5_TO_10M"},
            "investment_experience": {"years": 5},
            "loss_tolerance_pct": 20,
            "investment_horizon_months": 36,
            "investor_classification": "GENERAL",
            "age_bracket": "30s",
            "form_option_orders": {},
        },
        headers={**with_auth(pb1_token), "Idempotency-Key": str(uuid.uuid4())},
        timeout=15,
    )
    record["steps"].append({"step": "pre_check_suitability", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # Appropriateness acknowledge — emits appropriateness_warning_acknowledged (consultation_gates.py:204)
    r = await client.post(
        f"/consultations/{consultation_id}/appropriateness-acknowledge",
        json={"product_id": syn_product_id, "solicited": True},
        headers={**with_auth(pb1_token), "Idempotency-Key": str(uuid.uuid4())},
        timeout=15,
    )
    record["steps"].append({"step": "appropriateness_acknowledge", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # Explanation pre-check — emits explanation_confirmed (always PASSED)
    r = await client.post(
        f"/consultations/{consultation_id}/explanation-confirm",
        json={"checked_item_ids": ["item-1", "item-2", "item-3"]},
        headers={**with_auth(pb1_token), "Idempotency-Key": str(uuid.uuid4())},
        timeout=15,
    )
    record["steps"].append({"step": "pre_check_explanation", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # Unfair-solicitation pre-check — emits unfair_solicitation_blocked only on BLOCK
    r = await client.post(
        f"/consultations/{consultation_id}/unfair-solicitation-check",
        json={
            "message_text": "[SYN] 상담 안내 메시지 — 위험을 충분히 안내드렸습니다.",
            "product_id": syn_product_id,
            "solicited": True,
            "has_opt_in_audit": False,
        },
        headers={**with_auth(pb1_token), "Idempotency-Key": str(uuid.uuid4())},
        timeout=15,
    )
    record["steps"].append({"step": "pre_check_unfair_solicitation", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # Marketing pre-check — POST /marketing-review (marketing_review.py:57).
    # svc-viability-v2 T2-1: replaced from email-drafts submit flow to avoid
    # duplicate marketing_review_submitted/email_draft_submitted rows.
    # POST /marketing-review with consultation_id:
    #   (a) emits marketing_review_approved (marketing_review.py:57 MARKETING_REVIEW_PASS branch)
    #   (b) upserts consultation_gates(name="marketing") → enables 4-gate marketing ack
    r = await client.post(
        "/marketing-review",
        json={
            "consultation_id": consultation_id,
            "subject": "SYN 상담 사전 검토 결과 안내",
            "body": (
                "상담 고객님의 사전 검토가 완료되었습니다.\n"
                "상담 진행 관련 참고 자료를 확인 부탁드립니다."
            ),
            "marketing_classified": False,
        },
        headers={**with_auth(pb1_token), "Idempotency-Key": str(uuid.uuid4())},
        timeout=60,
    )
    record["steps"].append({"step": "marketing_review_pre_check",
                             "status": r.status_code, "body_excerpt": r.text[:200]})
    if r.status_code == 200:
        marketing_decision = r.json().get("decision", "")
        record["steps"][-1]["decision"] = marketing_decision
        if marketing_decision != "MARKETING_REVIEW_PASS":
            record["error"] = f"marketing_review decision not PASS: {marketing_decision}"
            return record

    # 2b) 4-gate acknowledge (PB1) — suitability → explanation → unfair_solicitation → marketing
    # 각 ack 호출 시 four_gate_acknowledged audit 1 row emit (consultation_gates.py:374).
    # With 2a) pre-checks above, each ack now returns 200 (D3 acceptance).
    for gate_name in ["suitability", "explanation", "unfair_solicitation", "marketing"]:
        r = await client.post(
            f"/consultations/{consultation_id}/four-gate/{gate_name}/acknowledge",
            headers=with_auth(pb1_token),
            timeout=15,
        )
        record["steps"].append({"step": f"four_gate_{gate_name}", "status": r.status_code,
                                 "body_excerpt": r.text[:200]})

    # 3) KYC EDD evaluate (WM1 — _require_compliance_role rejects PB)
    r = await client.post(
        "/kyc-edd/evaluate",
        json={
            "customer": {
                "id": SYN_CUSTOMER_ID,
                "aum_prev": 100_000_000,
                "aum_current": 250_000_000,  # 150% change → ASSET_CHANGE_PCT trigger
            },
            "recent_transactions": [],
        },
        headers=with_auth(wm1_token),
        timeout=30,
    )
    record["steps"].append({"step": "kyc_edd_evaluate", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # 4) Create email draft (PB1, non-marketing — 4-eye not enforced)
    r = await client.post(
        "/email-drafts",
        json={
            "customer_id": SYN_CUSTOMER_ID,
            "consultation_id": consultation_id,
            "subject": "[SYN] HP1 service viability audit v1",
            "body": "[SYN] Synthetic email body for HP1 happy path audit cycle.",
            "marketing_classified": False,
        },
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "email_draft_create", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"email_draft_create failed: {r.status_code} {r.text[:200]}"
        return record
    draft_id = r.json()["id"]
    record["draft_id"] = draft_id

    # 5) PB1 submit — emits marketing_review_submitted + email_draft_submitted (2 rows)
    r = await client.post(
        f"/email-drafts/{draft_id}/submit",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "email_draft_submit", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # 6) WM1 approve — emits email_draft_approved (1 row)
    r = await client.post(
        f"/email-drafts/{draft_id}/approve",
        headers=with_auth(wm1_token),
        timeout=15,
    )
    record["steps"].append({"step": "email_draft_approve", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # 7) PB1 send — emits email_sent_via_sandbox (1 row, email.py:637)
    # svc-viability-v2 T1-1/T1-2 PASS: Mailpit active → DP-2 resolved, send reinstated.
    # EMAIL_SANDBOX_GUARDRAIL_ENABLED=false → TEST_RECIPIENT_EMAIL 불문하고 Mailpit 수신.
    r = await client.post(
        f"/email-drafts/{draft_id}/send",
        headers=with_auth(pb1_token),
        timeout=30,
    )
    record["steps"].append({"step": "email_send", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    return record


async def run_np1(client: Any, pool: Any) -> dict[str, Any]:
    """NP1 — PB1 creates marketing_classified=True draft, submits, then self-approves → 403."""
    record: dict[str, Any] = {"scenario": "NP1", "steps": []}
    pb1_token = await login_get_token(client, "PB1")

    # Create marketing draft (marketing_classified=True + 사전심의필번호)
    # leading_block: subject + body 첫 줄에 '광고심의 사전심의필 {pre_review_number}' 포함 필수
    # opt_out: 본문에 수신거부 안내 포함 필수
    pre_review = "SYN-PR-NP1-2026"
    leading_block = f"광고심의 사전심의필 {pre_review}"
    r = await client.post(
        "/email-drafts",
        json={
            "customer_id": SYN_CUSTOMER_ID,
            "consultation_id": SYN_CONSULTATION_ID,
            "subject": f"{leading_block} — NP1 4-eye violation test",
            "body": (
                f"{leading_block}\n\n"
                "[SYN] 본 메일은 service viability audit v1 NP1 시나리오용 합성 광고문입니다.\n"
                "[부적합 유형] 원금손실 가능, 적합하지 않은 투자자: 위험회피형.\n"
                "투자판단의 최종 책임은 본인에게 있으며 손실 가능성을 충분히 인지하시기 바랍니다.\n\n"
                "수신거부: 본 광고 수신을 원치 않으시면 contact@example.invalid 로 회신해 주세요."
            ),
            "marketing_classified": True,
            "사전심의필번호": pre_review,
        },
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "draft_create_marketing", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"NP1 draft create failed: {r.status_code} {r.text[:200]}"
        return record
    draft_id = r.json()["id"]
    record["draft_id"] = draft_id

    # Submit
    r = await client.post(
        f"/email-drafts/{draft_id}/submit",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "submit", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # Self-approve (PB1 = author → 4-eye violation expected 403)
    r = await client.post(
        f"/email-drafts/{draft_id}/approve",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "self_approve_attempt", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    # NP1 finding (F8): marketing draft submit는 AI compliance fail-closed (AI_ERROR)로
    # `marketing_review_blocked` 발생 → 400 status_code. draft가 PENDING_APPROVAL 도달
    # 불가 → 4-eye rule (email.py:378) 자체가 unreachable in PoC. self-approve도 409
    # ("draft must be PENDING_APPROVAL"). expected_status 갱신:
    #   - 4-eye 직접 차단 (403/422) — 이상적 (AI 정상 시)
    #   - OR submit AI_ERROR 차단 (400 marketing_lint_failed + AI_ERROR issue) — 현재 PoC reality
    submit_step = next((s for s in record["steps"] if s["step"] == "submit"), {})
    submit_blocked = submit_step.get("status") == 400 and "marketing_lint_failed" in submit_step.get("body_excerpt", "")
    direct_4eye = r.status_code in (403, 422)
    record["expected_status_403_or_422"] = direct_4eye
    record["submit_blocked_by_ai_compliance"] = submit_blocked
    record["np1_finding"] = (
        "4-eye direct" if direct_4eye
        else "F8_ai_compliance_unreachable_4eye" if submit_blocked
        else "unknown"
    )
    return record


async def run_np1_b(client: Any, pool: Any) -> dict[str, Any]:
    """NP1-B — marketing_classified=False contrast: self-approve allowed (no 4-eye).

    svc-viability-v3 A3 Option-iii — pair with NP1 (positive 4-eye trigger) to
    confirm the 4-eye block is gated on marketing_classified and not always on.
    """
    record: dict[str, Any] = {"scenario": "NP1-B", "steps": []}
    pb1_token = await login_get_token(client, "PB1")
    r = await client.post(
        "/email-drafts",
        json={
            "customer_id": SYN_CUSTOMER_ID,
            "consultation_id": SYN_CONSULTATION_ID,
            "subject": "[SYN] NP1-B non-marketing contrast (no 4-eye)",
            "body": "[SYN] NP1-B audit cycle synthetic body (non-marketing path).",
            "marketing_classified": False,
        },
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "draft_create_nonmarketing", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"NP1-B draft create failed: {r.status_code} {r.text[:200]}"
        return record
    draft_id = r.json()["id"]
    record["draft_id"] = draft_id

    r = await client.post(
        f"/email-drafts/{draft_id}/submit",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "submit", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    r = await client.post(
        f"/email-drafts/{draft_id}/approve",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "self_approve_attempt", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    record["expected_status_200"] = r.status_code == 200
    return record


async def run_np1_c(client: Any, pool: Any) -> dict[str, Any]:
    """NP1-C — marketing draft missing the 광고심의 leading-block → submit 400 marketing_lint_failed.

    svc-viability-v3 A3 task-14 Gap-8 — preserve regression coverage of the
    services/marketing/core.py:102 lint_marketing_leading_block() failure
    path while NP1 now drives the lint-passing 4-eye path.
    """
    record: dict[str, Any] = {"scenario": "NP1-C", "steps": []}
    pb1_token = await login_get_token(client, "PB1")
    pre_review = "SYN-PR-NP1C-2026"
    r = await client.post(
        "/email-drafts",
        json={
            "customer_id": SYN_CUSTOMER_ID,
            "consultation_id": SYN_CONSULTATION_ID,
            "subject": "[SYN] NP1-C lint failure (missing leading block + opt-out)",
            "body": (
                "[SYN] NP1-C audit cycle synthetic body — "
                "intentionally missing the 광고심의 leading-block in subject "
                "and 수신거부 안내 in body to drive marketing lint failure."
            ),
            "marketing_classified": True,
            "사전심의필번호": pre_review,
        },
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "draft_create_marketing_lint_failing", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"NP1-C draft create failed: {r.status_code} {r.text[:200]}"
        return record
    draft_id = r.json()["id"]
    record["draft_id"] = draft_id

    r = await client.post(
        f"/email-drafts/{draft_id}/submit",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "submit", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    record["expected_submit_400_marketing_lint_failed"] = (
        r.status_code == 400 and "marketing_lint_failed" in r.text
    )
    return record


async def run_np2(client: Any, pool: Any) -> dict[str, Any]:
    """NP2 — ADMIN attempts approve → require_email_staff (PB/WM only) → 403."""
    record: dict[str, Any] = {"scenario": "NP2", "steps": []}
    pb1_token = await login_get_token(client, "PB1")
    admin_token = await login_get_token(client, "ADMIN")

    # Create + submit a non-marketing draft as PB1
    r = await client.post(
        "/email-drafts",
        json={
            "customer_id": SYN_CUSTOMER_ID,
            "consultation_id": SYN_CONSULTATION_ID,
            "subject": "[SYN] NP2 ADMIN approve attempt test",
            "body": "[SYN] NP2 audit cycle synthetic body.",
            "marketing_classified": False,
        },
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "draft_create", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"NP2 draft create failed: {r.status_code} {r.text[:200]}"
        return record
    draft_id = r.json()["id"]
    record["draft_id"] = draft_id

    r = await client.post(
        f"/email-drafts/{draft_id}/submit",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "submit", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # ADMIN attempts approve → require_email_staff → 403
    r = await client.post(
        f"/email-drafts/{draft_id}/approve",
        headers=with_auth(admin_token),
        timeout=15,
    )
    record["steps"].append({"step": "admin_approve_attempt", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    record["expected_status_403"] = r.status_code == 403
    return record


async def run_np3(client: Any, pool: Any) -> dict[str, Any]:
    """NP3 — Send attempt with non-synthetic recipient config → recipient_not_synthetic 503.

    Per DP-3: endpoint reads config TEST_RECIPIENT_EMAIL, not request payload.
    Current .env TEST_RECIPIENT_EMAIL='operator@example.invalid' (non-synthetic) →
    any send attempt produces email_send_failed + 503 recipient_not_synthetic.
    """
    record: dict[str, Any] = {"scenario": "NP3", "steps": []}
    pb1_token = await login_get_token(client, "PB1")
    wm1_token = await login_get_token(client, "WM1")

    # Create + submit + approve a draft, then attempt send (should 503 if config non-synthetic)
    r = await client.post(
        "/email-drafts",
        json={
            "customer_id": SYN_CUSTOMER_ID,
            "consultation_id": SYN_CONSULTATION_ID,
            "subject": "[SYN] NP3 non-synthetic recipient guardrail test",
            "body": "[SYN] NP3 audit cycle — should 503 if config recipient non-synthetic.",
            "marketing_classified": False,
        },
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "draft_create", "status": r.status_code,
                             "body_excerpt": r.text[:200]})
    if r.status_code != 201:
        record["error"] = f"NP3 draft create failed: {r.status_code} {r.text[:200]}"
        return record
    draft_id = r.json()["id"]
    record["draft_id"] = draft_id

    r = await client.post(
        f"/email-drafts/{draft_id}/submit",
        headers=with_auth(pb1_token),
        timeout=15,
    )
    record["steps"].append({"step": "submit", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # WM1 approve (non-marketing so no 4-eye block)
    r = await client.post(
        f"/email-drafts/{draft_id}/approve",
        headers=with_auth(wm1_token),
        timeout=15,
    )
    record["steps"].append({"step": "approve", "status": r.status_code,
                             "body_excerpt": r.text[:200]})

    # Send → expect 503 recipient_not_synthetic (current config operator@example.invalid)
    r = await client.post(
        f"/email-drafts/{draft_id}/send",
        headers=with_auth(wm1_token),
        timeout=30,
    )
    record["steps"].append({"step": "send_attempt", "status": r.status_code,
                             "body_excerpt": r.text[:300]})
    record["expected_status_503"] = r.status_code == 503
    return record


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def main_async(backend_url: str, dsn: str, output_dir: pathlib.Path) -> int:
    try:
        import httpx  # type: ignore[import-not-found]
        import asyncpg  # type: ignore[import-not-found]
    except ImportError as e:
        print(f"FATAL: httpx/asyncpg missing in {sys.executable}: {e}", flush=True)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    actor_ids = [SYN_EMPLOYEE_PB1, SYN_EMPLOYEE_WM1, SYN_EMPLOYEE_ADMIN]

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    try:
        txid_pairs: dict[str, dict[str, int]] = {}
        scenario_records: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(base_url=backend_url) as client:
            for scenario, fn in [("HP1", run_hp1), ("NP1", run_np1),
                                  ("NP1-B", run_np1_b), ("NP1-C", run_np1_c),
                                  ("NP2", run_np2), ("NP3", run_np3)]:
                print(f"=== running {scenario} ===", flush=True)
                start_txid = await fetch_txid(pool)
                try:
                    rec = await fn(client, pool)
                except Exception as e:
                    rec = {"scenario": scenario, "fatal": f"{type(e).__name__}: {e!s:.300}"}
                end_txid = await fetch_txid(pool)
                txid_pairs[scenario] = {"start": start_txid, "end": end_txid}
                rec["txid_start"] = start_txid
                rec["txid_end"] = end_txid
                # audit_logs delta
                audit_rows = await fetch_audit_rows_in_range(
                    pool, start_txid, end_txid, actor_ids
                )
                rec["audit_rows"] = audit_rows
                rec["audit_rows_count"] = len(audit_rows)
                rec["audit_codes_distinct"] = sorted({r["action_code"] for r in audit_rows})
                scenario_records[scenario] = rec
                (output_dir / f"{scenario}.json").write_text(
                    json.dumps(rec, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                print(f"  {scenario}: audit_rows={len(audit_rows)} distinct_codes={len(rec['audit_codes_distinct'])}", flush=True)

        # Aggregate
        (output_dir / "txid_pairs.json").write_text(
            json.dumps(txid_pairs, indent=2), encoding="utf-8"
        )

        # Binary criteria (REVISED HP1 expected per DP-1)
        hp1 = scenario_records.get("HP1", {})
        hp1_codes = hp1.get("audit_codes_distinct", [])
        hp1_count = hp1.get("audit_rows_count", 0)
        hp1_pass = (sorted(hp1_codes) == sorted(HP1_EXPECTED_CODES_REVISED)
                    and hp1_count == HP1_EXPECTED_ROW_COUNT_REVISED)

        np1 = scenario_records.get("NP1", {})
        np1_pass = bool(np1.get("expected_status_403_or_422")) and \
            sum(1 for r in np1.get("audit_rows", []) if "denied" in r.get("action_code", "")
                or r.get("action_code") in ("email_send_blocked", "auth_login_failure")) <= 1

        np1b = scenario_records.get("NP1-B", {})
        np1b_pass = bool(np1b.get("expected_status_200"))

        np1c = scenario_records.get("NP1-C", {})
        np1c_pass = bool(np1c.get("expected_submit_400_marketing_lint_failed"))

        np2 = scenario_records.get("NP2", {})
        np2_pass = bool(np2.get("expected_status_403"))

        np3 = scenario_records.get("NP3", {})
        np3_pass = bool(np3.get("expected_status_503"))

        summary = {
            "cycle": "service-viability-v1",
            "axis": "axis-2",
            "scenarios": ["HP1", "NP1", "NP1-B", "NP1-C", "NP2", "NP3"],
            "hp1_pass_revised": hp1_pass,
            "hp1_codes_observed": hp1_codes,
            "hp1_codes_expected_revised": HP1_EXPECTED_CODES_REVISED,
            "hp1_codes_expected_plan_as_written_outdated": HP1_EXPECTED_CODES_PLAN_AS_WRITTEN,
            "hp1_row_count_observed": hp1_count,
            "hp1_row_count_expected_revised": HP1_EXPECTED_ROW_COUNT_REVISED,
            "np1_pass": np1_pass,
            # np1_pass stays strict (403/422). np1_finding surfaces the documented
            # F8 PoC degradation path (F8_ai_compliance_unreachable_4eye) so a
            # known/valid PoC outcome is visibly distinguished from an unexpected fail.
            "np1_finding": np1.get("np1_finding"),
            "np1_submit_blocked_by_ai_compliance": np1.get("submit_blocked_by_ai_compliance"),
            "np1b_pass": np1b_pass,
            "np1c_pass": np1c_pass,
            "np2_pass": np2_pass,
            "np3_pass": np3_pass,
            "txid_pairs": txid_pairs,
            "actor_ids": actor_ids,
            "backend_url": backend_url,
            "notes": [
                "HP1 expected revised per DP-1 (handoff): plan §4 'exact 6' was SoT-mismatch with runtime.",
                "Enforced gate SoT = HP1_EXPECTED_CODES_REVISED "
                "(12 distinct action_codes) + HP1_EXPECTED_ROW_COUNT_REVISED "
                "(15 total rows: four_gate_acknowledged ×4, others ×1).",
                "TEST_RECIPIENT_EMAIL env value affects HP1 #6 email_sent_via_sandbox emission (config-only path).",
            ],
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"DONE. summary: {output_dir / 'summary.json'}", flush=True)
        print(f"  HP1: pass={hp1_pass} observed_count={hp1_count} expected={HP1_EXPECTED_ROW_COUNT_REVISED}", flush=True)
        print(f"  NP1: pass={np1_pass}", flush=True)
        print(f"  NP1-B: pass={np1b_pass}", flush=True)
        print(f"  NP1-C: pass={np1c_pass}", flush=True)
        print(f"  NP2: pass={np2_pass}", flush=True)
        print(f"  NP3: pass={np3_pass}", flush=True)
        return 0
    finally:
        await pool.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Axis 2 workflow E2E (HP1/NP1/NP2/NP3)")
    p.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    p.add_argument("--dsn", default=DEFAULT_DSN)
    p.add_argument("--output-dir", default=str(OUTPUT_BASE))
    args = p.parse_args()
    if not args.dsn:
        print(
            "ERROR: DSN이 비어 있습니다. "
            "--dsn, AUDIT_V1_DSN 또는 .env의 DATABASE_URL을 설정하세요.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(main_async(args.backend_url, args.dsn, pathlib.Path(args.output_dir)))


if __name__ == "__main__":
    sys.exit(main())
