"""Marketing review gate router — REG-02 T224 / 금소법 §광고규제."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    request_audit_context,
)
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import suitability as suitability_repo
from apps.api.harness.services.marketing import run_marketing_gate

router = APIRouter(tags=["marketing-review"])


@router.post("/marketing-review", status_code=status.HTTP_200_OK)  # type: ignore[union-attr]
async def submit_marketing_review(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run 광고심의 compliance gate on marketing copy (REG-02 T224).

    Evaluates static lint rules (단정문구/손실보전/이익보장) then calls the
    marketing service's AI compliance_check gate.  Returns
    ``decision: MARKETING_REVIEW_PASS | MARKETING_REVIEW_BLOCK``.

    The gate result is optionally persisted to ``consultation_gates`` when
    ``consultation_id`` is provided in the payload.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)

    subject: str = str(payload.get("subject") or "")
    body: str = str(payload.get("body") or payload.get("message_text") or "")
    if not body.strip():
        raise HTTPException(status_code=422, detail="body (or message_text) is required")

    consultation_id: str | None = payload.get("consultation_id")
    marketing_classified: bool = bool(payload.get("marketing_classified", False))
    pre_review_number: str | None = payload.get("pre_review_number")

    gate_result = await run_marketing_gate(
        subject=subject,
        body=body,
        marketing_classified=marketing_classified,
        pre_review_number=pre_review_number,
    )

    decision = gate_result.decision
    action_code = (
        "marketing_review_approved"
        if decision == "MARKETING_REVIEW_PASS"
        else "marketing_review_rejected"
    )
    issue_codes: list[str] = list(gate_result.issue_codes or [])

    async with get_pool(request).acquire() as connection:
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code=action_code,
            resource_type="marketing_review",
            resource_id=consultation_id,
            detail={"decision": decision, "issue_codes": issue_codes},
            **request_audit_context(request),
        )

        if consultation_id:
            await suitability_repo.upsert_gate(
                connection,
                consultation_id=consultation_id,
                gate_name="marketing",
                gate_status="PASSED" if decision == "MARKETING_REVIEW_PASS" else "BLOCKED",
                gate_evidence_json={
                    "decision": decision,
                    "classification": gate_result.classification,
                    "issue_codes": issue_codes,
                },
            )

    return {
        "decision": decision,
        "classification": gate_result.classification,
        "issue_codes": issue_codes,
        "ai_reasoning": gate_result.ai_reasoning_redacted,
        "consultation_id": consultation_id,
    }
