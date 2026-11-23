"""AI job and AI output routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_async_redis,
    get_pool,
    get_request_config,
    request_audit_context,
)
from apps.api.harness.batch.documents import sanitize_untrusted_document_text
from apps.api.harness.repositories import ai as ai_repo
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import documents as document_repo
from apps.api.harness.repositories import readiness as readiness_repo
from apps.api.harness.services.ai.content_safety import check_content_safety
from apps.api.harness.services.ai.llm_redactor import redact_llm_output
from apps.api.harness.services.ai.output_quality import (
    SYNTHETIC_ADVISORY_NOTICE,
    assess_faithfulness,
)
from apps.api.harness.services.ai.token_meter import (
    check_token_rate,
    record_azure_token_consumption,
)
from apps.api.harness.services.ai_jobs import (
    call_privileged_llm,
    call_quarantined_llm,
    prompt_hash_from_payload,
)

router = APIRouter(tags=["ai"])

RAG_SOURCE_TYPES = {"DART", "REG_PAGE", "RESEARCH", "MANUAL", "WEB_SEARCH"}


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_types(payload: dict[str, Any]) -> list[str] | None:
    raw = payload.get("filter_source_types")
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="filter_source_types must be an array")
    values = [str(item).strip() for item in raw if str(item).strip()]
    unsupported = sorted(set(values) - RAG_SOURCE_TYPES)
    if unsupported:
        raise HTTPException(status_code=400, detail=f"unsupported source type: {unsupported[0]}")
    return values or None


def _datetime_filter(payload: dict[str, Any], key: str) -> datetime | None:
    text = _payload_string(payload, key)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _float_score(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _citation_from_chunk(row: dict[str, Any], text: str) -> dict[str, Any]:
    published_at = row.get("published_at") or row.get("document_published_at")
    return {
        "chunk_id": str(row["chunk_id"]),
        "document_title": row.get("document_title"),
        "source_type_code": row.get("source_type_code"),
        "provider_code": row.get("provider_code") or row.get("source_type_code"),
        "source_document_id": row.get("receipt_no") or row.get("document_source_id"),
        "receipt_no": row.get("receipt_no"),
        "corp_code": row.get("corp_code"),
        "source_url": row.get("source_url") or row.get("document_source_url"),
        "published_at": _json_safe(published_at),
        "chunk_no": row.get("chunk_no"),
        "section_path": row.get("section_path"),
        "parser_version": row.get("parser_version"),
        "quote": text[:280],
    }


def _build_cited_answer(
    question: str, chunks: list[dict[str, Any]]
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the citation-grounded answer body and a separate attribution note.

    Returns ``(answer_body, attribution_note, citations, evidence_rows)``.

    ``answer_body`` contains ONLY the citation-derived statements
    (``[1] ... [2] ...``). ``attribution_note`` carries the disclaimer
    + question echo that is meta-content about the answer, not derived
    from any chunk. Keeping them separate lets the API consumer render
    both — and lets the RAGAS Faithfulness measurement score only the
    citation-derived body, eliminating the structurally-un-entailed
    meta-statement that drags per-trace pass rate (ADR-009 §G1
    per-trace root cause analysis + ralplan v4 C3).
    """
    citations: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    for row in chunks[:5]:
        sanitized = sanitize_untrusted_document_text(str(row.get("chunk_text") or ""))
        if not sanitized.text:
            continue
        citation = _citation_from_chunk(row, sanitized.text)
        if not citation.get("chunk_id") or not citation.get("source_url"):
            continue
        citations.append(citation)
        evidence_rows.append(row)
        answer_parts.append(f"[{len(citations)}] {sanitized.text[:360]}")
    if not citations:
        return "", "", [], []
    attribution_note = (
        f"아래 답변은 검색된 승인 청크만 발췌한 근거 기반 요약입니다. 질문: {question}"
    )
    answer_body = " ".join(answer_parts)
    return answer_body, attribution_note, citations, evidence_rows


RAG_FAIL_CLOSED_CODES = frozenset({
    "NO_CITATION",
    "SOURCE_MISMATCH",
    "EMPTY_SANITIZED_TEXT",
    "UNSUPPORTED_FILTER",
    "QUARANTINED_CONTEXT",
    "DIMENSION_MISMATCH",
    "LOW_FAITHFULNESS",
    "PROMPT_INJECTION_DETECTED",
    "CONTENT_SAFETY_BLOCKED",   # W3-T6: Azure Content Safety pre/post flag
})


def _blocked_output(reason: str, *, fail_closed_reason_code: str = "NO_CITATION") -> dict[str, Any]:
    if fail_closed_reason_code not in RAG_FAIL_CLOSED_CODES:
        fail_closed_reason_code = "NO_CITATION"
    return {
        "status": "BLOCKED_WITH_CITATION_GATE",
        "reason": reason,
        "fail_closed_reason_code": fail_closed_reason_code,
        "grounding_required": True,
    }


def _rag_quality_fields(
    answer: str | None, citations: list[dict[str, Any]]
) -> dict[str, Any]:
    """P2-2: data-quality disclosure + deterministic faithfulness for every RAG reply.

    The RAG QA route returns AI-derived text straight to a banker, but its reply
    carried no data-quality disclosure and no grounding signal — a synthetic /
    unverified answer could read as established fact. Every READY and BLOCKED reply
    now carries the static synthetic disclosure plus a faithfulness assessment of
    the answer against its citations (the only grounding a RAG answer has).
    ``require_disclosure`` is False because the disclosure lives in
    ``data_quality_notice`` rather than inside the answer text; the gate here flags
    answer figures absent from the cited sources (e.g. a generative-path
    fabrication). Observability/flagging only — it does not block the response.
    """
    grounding = {"citations": citations} if citations else None
    return {
        "data_quality_notice": SYNTHETIC_ADVISORY_NOTICE,
        "faithfulness": assess_faithfulness(
            output_text=answer or "",
            model_input=grounding,
            require_disclosure=False,
        ),
    }


@router.get("/ai-jobs/{job_id}")  # type: ignore[union-attr]
async def get_ai_job(
    request: Request,
    job_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read authorized durable AI job status."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        job = await ai_repo.get_ai_job(
            connection,
            job_id=str(job_id),
            role_code=actor.role_code,
            employee_id=actor.employee_id,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="ai job not found")
        # Wave-Audit-Defect-Fix B7: sensitive read trail for /ai-jobs/{id}.
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="ai_job_get",
            resource_type="ai_job",
            resource_id=str(job_id),
            detail={"job_type_code": job.get("job_type_code")},
            **request_audit_context(request),
        )
    return job


@router.get("/ai-outputs/{output_id}")  # type: ignore[union-attr]
async def get_ai_output(
    request: Request,
    output_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read authorized AI output metadata/detail."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        output = await ai_repo.get_ai_output(
            connection,
            output_id=str(output_id),
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
        )
        if output is None:
            raise HTTPException(status_code=404, detail="ai output not found")
        # output_json is JSONB and comes back from asyncpg as a JSON string; parse it
        # so the API exposes an object. The frontend AIMetadataFooter reads nested
        # fields (synthetic / data_quality_notice / faithfulness / _pii_masked_categories)
        # which were previously unreachable because output_json arrived as a string.
        raw_output_json = output.get("output_json")
        if isinstance(raw_output_json, str):
            try:
                output["output_json"] = json.loads(raw_output_json)
            except (json.JSONDecodeError, TypeError):
                output["output_json"] = {}
        # Wave-Audit-Defect-Fix B7: sensitive read trail for /ai-outputs/{id}.
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="ai_output_get",
            resource_type="ai_output",
            resource_id=str(output_id),
            detail={"agent_id": output.get("agent_id")},
            **request_audit_context(request),
        )
    return output


@router.post("/rag/query")  # type: ignore[union-attr]
@router.post("/rag/qa")  # type: ignore[union-attr]
async def rag_query(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
    dry_run: bool = Query(default=False, description="DELTA-4 test-double: accept param (rag_qa uses extractive path; Azure generative path already gated by AZURE_GENERATIVE_RAG_ENABLED)"),
) -> dict[str, Any]:
    """Answer only from embedded cited chunks; otherwise fail closed.

    REG-04 dual-LLM contract (ADR-005): injection pre-check via
    :mod:`apps.api.harness.services.ai.injection_detector`. PoC default is
    extractive citation-gate (no generative Azure call) for token-budget
    discipline; full dual-LLM Azure path remains a Wave 5 hardening lane.
    """

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    if actor.role_code == "AUDIT_VIEWER":
        raise HTTPException(status_code=403, detail="staff AI role required")
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    # ── LLM10: per-employee token rate ceiling (W3-T6) ────────────────────────
    _estimated_tokens = len(question) // 4 + 256  # rough pre-call estimate
    # Wave-Audit-Defect-Fix B8: previously `create_redis_client(config.redis)` ran
    # per-request, opening a fresh Redis connection on every /rag/query call and
    # leaking sockets under load. Use the request-scoped async Redis client from
    # dependencies (single pool shared across requests).
    try:
        _redis = get_async_redis(request)
    except Exception:  # noqa: BLE001
        _redis = None
    _rate = check_token_rate(actor.employee_id, _estimated_tokens, _redis)
    if _rate.exceeded:
        async with get_pool(request).acquire() as connection:
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="ai_token_rate_limited",
                resource_type="rag_query",
                resource_id=None,
                detail={
                    "reason": _rate.reason,
                    "tokens_consumed_1m": _rate.tokens_consumed_1m,
                    "tokens_consumed_1h": _rate.tokens_consumed_1h,
                },
                ip_address=None,
                user_agent=request.headers.get("user-agent"),
            )
        raise HTTPException(
            status_code=429,
            detail=f"AI token rate limit exceeded ({_rate.reason}). Retry later.",
        )

    # ── Content Safety pre-check on user input (W3-T6) ───────────────────────
    _cs_input = check_content_safety(question, context="input")
    if _cs_input.blocked:
        async with get_pool(request).acquire() as connection:
            output = _blocked_output(
                f"Content Safety blocked input: {_cs_input.categories_flagged}",
                fail_closed_reason_code="CONTENT_SAFETY_BLOCKED",
            )
            ai_output = await ai_repo.create_ai_output(
                connection,
                agent_id="rag_qa",
                model_name=config.ai.azure_deployment_name,
                resource_type="rag_query",
                resource_id=None,
                job_id=None,
                prompt_hash=prompt_hash_from_payload({"question_length": len(question)}),
                output=output,
                fail_closed_reason_code=output.get("fail_closed_reason_code"),
                question_text=question,
            )
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="ai_fail_closed",
                resource_type="ai_output",
                resource_id=str(ai_output["id"]),
                detail={
                    "fail_closed_reason_code": "CONTENT_SAFETY_BLOCKED",
                    "categories_flagged": _cs_input.categories_flagged,
                },
                ip_address=None,
                user_agent=request.headers.get("user-agent"),
            )
        return {
            "status_code": "BLOCKED",
            **_rag_quality_fields(None, []),
            "fail_closed_reason_code": output.get("fail_closed_reason_code"),
            "answer": None,
            "confidence": 0.0,
            "citations": [],
            "caveat": output,
            "output_id": str(ai_output["id"]),
            "generated_at": ai_output["generated_at"],
            "model_name": ai_output["model_name"],
            "readiness": None,
        }

    from apps.api.harness.services.ai.injection_detector import detect_injection
    injection = detect_injection(question)
    if injection.detected:
        async with get_pool(request).acquire() as connection:
            output = _blocked_output(
                f"prompt-injection pattern matched: {injection.category}",
                fail_closed_reason_code="PROMPT_INJECTION_DETECTED",
            )
            ai_output = await ai_repo.create_ai_output(
                connection,
                agent_id="rag_qa",
                model_name=config.ai.azure_deployment_name,
                resource_type="rag_query",
                resource_id=None,
                job_id=None,
                prompt_hash=prompt_hash_from_payload({"question_length": len(question)}),
                output=output,
                fail_closed_reason_code=output.get("fail_closed_reason_code"),
                question_text=question,
            )
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="ai_injection_detected",
                resource_type="ai_output",
                resource_id=str(ai_output["id"]),
                detail={"category": injection.category, "pattern_id": injection.pattern_id},
                ip_address=None,
                user_agent=request.headers.get("user-agent"),
            )
        return {
            "status_code": "BLOCKED",
            **_rag_quality_fields(None, []),
            "fail_closed_reason_code": output.get("fail_closed_reason_code"),
            "answer": None,
            "confidence": 0.0,
            "citations": [],
            "caveat": output,
            "output_id": str(ai_output["id"]),
            "generated_at": ai_output["generated_at"],
            "model_name": ai_output["model_name"],
            "readiness": None,
        }

    source_types = _source_types(payload)
    corp_code = _payload_string(payload, "corp_code")
    receipt_no = _payload_string(payload, "receipt_no")
    provider_code = _payload_string(payload, "provider_code")
    published_from = _datetime_filter(payload, "published_from")
    published_to = _datetime_filter(payload, "published_to")

    async with get_pool(request).acquire() as connection:
        readiness = await readiness_repo.get_data_readiness(connection)
        chunks = await document_repo.search_rag_chunks(
            connection,
            question=question,
            source_types=source_types,
            corp_code=corp_code,
            receipt_no=receipt_no,
            provider_code=provider_code,
            published_from=published_from,
            published_to=published_to,
            limit=5,
        )
        answer, attribution_note, citations, evidence_rows = _build_cited_answer(question, chunks)
        if not citations:
            output = _blocked_output(
                "No embedded approved source chunk matched the question/filters"
            )
            ai_output = await ai_repo.create_ai_output(
                connection,
                agent_id="rag_qa",
                model_name=config.ai.azure_deployment_name,
                resource_type="rag_query",
                resource_id=None,
                job_id=None,
                prompt_hash=prompt_hash_from_payload({"question_length": len(question)}),
                output=output,
                fail_closed_reason_code=output.get("fail_closed_reason_code"),
                question_text=question,
            )
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                # Wave-Audit-Defect-Fix B9: AI_CALL_FAILED was an umbrella
                # code; the no-citation block is specifically a citation-gate
                # failure (not a provider/Azure failure). Split for audit
                # search precision. AI_CALL_FAILED canonical preserved for
                # legacy use; provider_failure now reserved for Azure-side
                # generative path errors.
                action_code="citation_gate_failed",
                resource_type="ai_output",
                resource_id=str(ai_output["id"]),
                detail=output,
                ip_address=None,
                user_agent=request.headers.get("user-agent"),
            )
            return {
                "status_code": "BLOCKED",
                **_rag_quality_fields(None, []),
                "fail_closed_reason_code": output.get("fail_closed_reason_code"),
                "answer": None,
                "confidence": 0.0,
                "citations": [],
                "caveat": output,
                "output_id": str(ai_output["id"]),
                "generated_at": ai_output["generated_at"],
                "model_name": ai_output["model_name"],
                "readiness": readiness["rag"],
            }

        confidence = min(0.9, 0.55 + 0.08 * len(citations))
        token_detail: dict[str, Any] = {}
        model_label = f"{config.ai.azure_deployment_name}+extractive-citation-gate"

        # ── Generative dual-LLM path (ADR-005, W3-T6) ────────────────────────
        # Activated when AZURE_GENERATIVE_RAG_ENABLED=true; falls back to
        # extractive citation gate when disabled or on Azure error.
        import os as _os
        if _os.getenv("AZURE_GENERATIVE_RAG_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
            q_out = await call_quarantined_llm(
                agent_id="rag_qa", chunks=chunks, question=question
            )
            if not q_out.get("error"):
                p_out = await call_privileged_llm(
                    agent_id="rag_qa",
                    quarantine_output=q_out,
                    question=question,
                    citations=citations,
                )
                if not p_out.get("error"):
                    # LLM07 redaction on privileged output (W3-T6)
                    redaction = redact_llm_output(p_out.get("answer", ""))
                    if redaction.leakage_detected:
                        await audit_repo.insert_audit_log(
                            connection,
                            actor_id=actor.employee_id,
                            action_code="ai_quarantine_triggered",
                            resource_type="rag_query",
                            resource_id=None,
                            detail={"patterns_matched": redaction.patterns_matched},
                            ip_address=None,
                            user_agent=request.headers.get("user-agent"),
                        )
                    answer = redaction.redacted_text if redaction.redacted_text else answer

                    # Content Safety post-check on AI output (W3-T6)
                    _cs_out = check_content_safety(answer, context="output")
                    if _cs_out.blocked:
                        answer = ""
                        confidence = 0.0

                    tok_in = p_out.get("tokens_in", 0) + q_out.get("_tokens_in", 0)
                    tok_out = p_out.get("tokens_out", 0) + q_out.get("_tokens_out", 0)
                    model_label = str(p_out.get("model", config.ai.azure_deployment_name))
                    token_detail = record_azure_token_consumption(
                        tokens_in=tok_in,
                        tokens_out=tok_out,
                        model=model_label,
                        agent_id="rag_qa",
                    )

        output = {
            "status": "ANSWERED_WITH_CITATIONS",
            "answer": answer,
            "attribution_note": attribution_note,
            "confidence": confidence,
            "citations": citations,
            "grounding_required": True,
        }
        ai_output = await ai_repo.create_ai_output(
            connection,
            agent_id="rag_qa",
            model_name=model_label,
            resource_type="rag_query",
            resource_id=None,
            job_id=None,
            prompt_hash=prompt_hash_from_payload(
                {
                    "question_length": len(question),
                    "source_types": source_types or [],
                    "corp_code": corp_code or "",
                    "receipt_no": receipt_no or "",
                }
            ),
            output=output,
            citations=citations,
            question_text=question,
        )
        for row, citation in zip(evidence_rows, citations, strict=False):
            source_document_id = str(citation.get("source_document_id") or row["chunk_id"])
            quote = str(citation.get("quote") or "")
            await document_repo.insert_rag_answer_evidence(
                connection,
                ai_output_id=str(ai_output["id"]),
                chunk_id=str(citation["chunk_id"]),
                source_document_id=source_document_id,
                quote_span={"start": 0, "end": len(quote), "text": quote},
                retrieval_score=_float_score(row.get("retrieval_score")),
                rerank_score=None,
                confidence=confidence,
            )
        audit_detail: dict[str, Any] = {
            "citations_count": len(citations),
            "grounding_required": True,
        }
        if token_detail:
            audit_detail["token_consumption"] = token_detail
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="AI_CALL_SUCCEEDED",
            resource_type="ai_output",
            resource_id=str(ai_output["id"]),
            detail=audit_detail,
            ip_address=None,
            user_agent=request.headers.get("user-agent"),
        )
    return {
        "status_code": "READY",
        **_rag_quality_fields(answer, citations),
        "answer": answer,
        "attribution_note": attribution_note,
        "confidence": confidence,
        "citations": citations,
        "caveat": {"grounding_required": True},
        "output_id": str(ai_output["id"]),
        "generated_at": ai_output["generated_at"],
        "model_name": ai_output["model_name"],
        "readiness": readiness["rag"],
    }
