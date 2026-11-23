"""email_draft AI agent — dual-LLM dispatcher (Wave 6.3 US-W63-2, R36).

ADR-005 §Status puts ``email_draft`` in the dual-LLM scope (3-agent set
together with ``rag_qa`` and ``consultation_briefing``). The worker entry
script (``scripts/run_ai_job_runner.py``) claims a PENDING ``ai_jobs`` row
with ``job_type_code='email_draft'`` and ``resource_type='email_drafts'``,
then calls ``run_email_draft`` to process it.

Flow:

1. Load the ``email_drafts`` row referenced by ``job['resource_id']``. Its
   ``body`` field is the PB's raw request (untrusted free-form text).
2. Quarantined lane: extract the intent (tone, customer concern, desired
   outcome) as structured JSON. No tool access; processed under
   ``_QUARANTINE_SYSTEM`` per ADR-005 §1.
3. Privileged lane: compose ``{"subject", "body"}`` from the quarantined
   intent. The PB's raw text is never re-introduced as free-form
   instructions — only as DATA inside ``<USER_DATA>`` markers.
4. Update ``email_drafts.subject``/``body``/``ai_generated_at``/
   ``ai_model_name`` and insert an ``ai_outputs`` audit row with
   ``agent_id='email_draft'``.
5. Return a short summary string; the worker writes it to
   ``ai_jobs.result_summary`` via ``mark_succeeded``.

Failure modes return ``RuntimeError`` (the worker's ``mark_failed`` records
``error_code`` + ``error_message``). The DB row is never partially updated
because the worker wraps the call in a transaction.
"""

from __future__ import annotations

import json
from typing import Any

from .ai.output_quality import SYNTHETIC_ADVISORY_NOTICE
from .ai_jobs import call_privileged_generic, call_quarantined_generic

# ── Dry-run synthetic fixtures (test-double dispatcher, DELTA-4 / G0a-1) ─────
_DRY_RUN_SUBJECT = "[SYN] 안녕하세요, 고객님의 포트폴리오 현황 안내드립니다"
_DRY_RUN_BODY = (
    "안녕하세요 고객님,\n\n"
    "최근 시장 변동성을 고려하여 포트폴리오 리밸런싱 시점을 점검해 드리고자 연락드렸습니다. "
    "현재 보유 자산 비중을 바탕으로 안정적인 자산 관리 방향을 제안드릴 수 있습니다.\n\n"
    "편하신 시간에 면담 일정을 잡아 주시면 자세한 사항을 말씀드리겠습니다.\n\n"
    "감사합니다.\n담당 PB 드림"
)


async def _dry_run_email_draft(conn: Any, job: dict[str, Any]) -> str:
    """Test-double dispatcher: synthetic Korean email content, no Azure call.

    Real DB writes (UPDATE email_drafts + INSERT ai_outputs) are preserved.
    Azure SDK call is replaced by canned fixture. tokens_in/tokens_out = 0.
    """
    resource_id = str(job.get("resource_id") or "00000000-0000-0000-0000-000000000001")
    job_id = str(job.get("id") or "00000000-0000-0000-0000-000000000002")
    model_name = "dry-run-mock"

    await conn.execute(UPDATE_DRAFT_SQL, resource_id, _DRY_RUN_SUBJECT, _DRY_RUN_BODY, model_name)

    output_payload = {
        "subject": _DRY_RUN_SUBJECT,
        "body_preview": _DRY_RUN_BODY[:200],
        "intent": {
            "customer_concern": "[SYN] 포트폴리오 점검",
            "tone": "professional",
            "desired_outcome": "[SYN] 면담 예약",
            "key_points": ["[SYN] 리밸런싱 제안"],
        },
        # P2-9: observability disclosure — the draft is composed over synthetic,
        # unverified customer context.
        "data_quality_notice": SYNTHETIC_ADVISORY_NOTICE,
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_dry_run": True,
    }
    await conn.execute(
        INSERT_AI_OUTPUT_SQL,
        model_name,
        resource_id,
        job_id,
        f"email_draft:dry_run:{resource_id}",
        json.dumps(output_payload, ensure_ascii=False),
        "[SYN] email draft dry-run synthetic request",
    )
    return f"email_draft {resource_id} dry_run synthetic (subject={len(_DRY_RUN_SUBJECT)}c)"

LOAD_DRAFT_SQL = """
/* sql_id: load_email_draft_for_ai_dispatch */
SELECT id, customer_id, employee_id, subject, body
FROM email_drafts
WHERE id = $1::uuid;
"""

UPDATE_DRAFT_SQL = """
/* sql_id: update_email_draft_from_ai_dispatch */
UPDATE email_drafts
SET subject = $2,
    body = $3,
    ai_generated_at = now(),
    ai_model_name = $4,
    updated_at = now()
WHERE id = $1::uuid;
"""

INSERT_AI_OUTPUT_SQL = """
/* sql_id: insert_ai_output_email_draft */
INSERT INTO ai_outputs(agent_id, model_name, generated_at, resource_type, resource_id, job_id,
                       prompt_hash, output_json, citations_json, fail_closed_reason_code, question_text)
VALUES ('email_draft', $1, now(), 'email_drafts', $2::uuid, $3::uuid, $4, $5::jsonb, '[]'::jsonb, NULL, $6)
RETURNING id;
"""


_QUARANTINE_PROMPT = (
    "Extract the PB's email intent. Return ONLY JSON: "
    '{"customer_concern": str, "tone": str, "desired_outcome": str, "key_points": [str]}.'
)

_PRIVILEGED_PROMPT = (
    "You are composing a professional Korean PB email to a customer. "
    "Return ONLY JSON: {\"subject\": str, \"body\": str}. "
    "The subject must be under 80 chars; the body must be under 1200 chars. "
    "Cite no external sources; this is a personal email reply, not a RAG answer."
)


async def run_email_draft(conn: Any, job: dict[str, Any]) -> str:
    """Worker dispatcher: process one PENDING email_draft ai_job.

    When ``job["dry_run"] is True`` the Azure SDK call is replaced by a canned
    Korean fixture (test-double dispatcher, DELTA-4 / G0a-1). Real DB writes
    and WS broadcast are preserved by the caller (ai_jobs_worker).
    """
    if job.get("dry_run"):
        return await _dry_run_email_draft(conn, job)

    if job.get("resource_type") not in ("email_draft", "email_drafts"):
        raise ValueError(
            f"email_draft dispatcher expects resource_type='email_draft' (or 'email_drafts'), "
            f"got {job.get('resource_type')!r}"
        )
    resource_id = job.get("resource_id")
    if resource_id is None:
        raise ValueError("email_draft job missing resource_id")

    row = await conn.fetchrow(LOAD_DRAFT_SQL, str(resource_id))
    if row is None:
        raise ValueError(f"email_drafts row not found: {resource_id}")

    user_request = (row["body"] or "").strip()
    if not user_request:
        raise ValueError(f"email_drafts.body is empty for {resource_id}")

    q_out = await call_quarantined_generic(
        agent_id="email_draft",
        system_prompt=_QUARANTINE_PROMPT,
        user_data_blocks=[f"<USER_DATA>\nPB request:\n{user_request}\n</USER_DATA>"],
        response_is_json=True,
    )
    if "error" in q_out:
        raise RuntimeError(f"email_draft quarantined LLM error: {q_out['error']}")

    intent_summary = json.dumps(
        {
            "customer_concern": q_out.get("customer_concern", ""),
            "tone": q_out.get("tone", ""),
            "desired_outcome": q_out.get("desired_outcome", ""),
            "key_points": q_out.get("key_points", []),
        },
        ensure_ascii=False,
    )

    p_out = await call_privileged_generic(
        agent_id="email_draft",
        system_prompt=_PRIVILEGED_PROMPT,
        data_blocks=[f"<USER_DATA>\nExtracted intent (quarantined lane output):\n{intent_summary}\n</USER_DATA>"],
        response_is_json=True,
    )
    if "error" in p_out:
        raise RuntimeError(f"email_draft privileged LLM error: {p_out['error']}")

    new_subject = str(p_out.get("subject", row["subject"]) or row["subject"])[:500]
    new_body = str(p_out.get("body", row["body"]) or row["body"])[:5000]
    model_name = str(p_out.get("_model") or "gpt-5.5")[:120]

    await conn.execute(UPDATE_DRAFT_SQL, str(resource_id), new_subject, new_body, model_name)

    output_payload = {
        "subject": new_subject,
        "body_preview": new_body[:200],
        "intent": json.loads(intent_summary),
        # P2-9: observability disclosure — the draft is composed over synthetic,
        # unverified customer context.
        "data_quality_notice": SYNTHETIC_ADVISORY_NOTICE,
        "_tokens_in": p_out.get("_tokens_in", 0),
        "_tokens_out": p_out.get("_tokens_out", 0),
    }
    prompt_hash = f"email_draft:{resource_id}"
    # V065 question_text: capture the PB's raw email request (the user's
    # intent the LLM is responding to). Trimmed to fit the column.
    question_text_value = user_request[:2000] if user_request else None
    await conn.execute(
        INSERT_AI_OUTPUT_SQL,
        model_name,
        str(resource_id),
        str(job["id"]),
        prompt_hash,
        json.dumps(output_payload, ensure_ascii=False),
        question_text_value,
    )

    return f"email_draft {resource_id} updated (subject={len(new_subject)}c, body={len(new_body)}c)"
