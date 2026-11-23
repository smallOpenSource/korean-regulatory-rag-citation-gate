"""금소법 §57/§69 위반 조항 코드 — violation_clause_code mapping (T213).

When a 4-gate or marketing-review check produces a BLOCKED outcome, the
gate_evidence_json should carry a machine-readable reference to the §
clause violated. This module owns the canonical mapping between the
operational reason_code values produced by upstream services and the
금소법 (Financial Consumer Protection Act) clause IDs, plus a helper
that decorates a BLOCKED reason dict with the resolved clause code.

REG-01 §5 cross-reference: this enables auto-generation of §57/§69
sanction-trace reports during audit review.
"""

from __future__ import annotations


# ─── Canonical clause catalogue ───────────────────────────────────────────────
# Keys are stable identifiers consumed by upstream BLOCKED-reason emitters;
# values record the article number, English handle, and Korean label.

VIOLATION_CLAUSES: dict[str, dict[str, str]] = {
    "SUITABILITY_FAILED": {
        "clause": "§17",
        "name": "suitability_principle",
        "label_ko": "적합성 원칙 위반",
    },
    "APPROPRIATENESS_FAILED": {
        "clause": "§18",
        "name": "appropriateness_principle",
        "label_ko": "적정성 원칙 위반",
    },
    "EXPLANATION_FAILED": {
        "clause": "§19",
        "name": "explanation_duty",
        "label_ko": "설명의무 위반",
    },
    "UNFAIR_PRACTICE_DETECTED": {
        "clause": "§20",
        "name": "unfair_business_practice",
        "label_ko": "불공정영업행위 금지 위반",
    },
    "IMPROPER_SOLICITATION": {
        "clause": "§21",
        "name": "improper_solicitation",
        "label_ko": "부당권유행위 금지 위반",
    },
    "MARKETING_REVIEW_MISSING": {
        "clause": "§22",
        "name": "advertising_regulation",
        "label_ko": "광고 규제 위반",
    },
    "CONTRACT_DOCUMENTS_MISSING": {
        "clause": "§23",
        "name": "contract_documents_duty",
        "label_ko": "계약서류 제공의무 위반",
    },
    "INFO_RETENTION_MISSING": {
        "clause": "§28",
        "name": "info_retention_and_access",
        "label_ko": "자료유지·열람권 위반",
    },
    "DAMAGES_LIABILITY": {
        "clause": "§44",
        "name": "damages_liability",
        "label_ko": "손해배상 책임",
    },
    "SUBSCRIPTION_WITHDRAWAL": {
        "clause": "§45",
        "name": "subscription_withdrawal",
        "label_ko": "청약 철회권",
    },
    "ILLEGAL_CONTRACT_TERMINATION": {
        "clause": "§47",
        "name": "illegal_contract_termination",
        "label_ko": "위법계약 해지권",
    },
}

CLAUSE_BY_REASON: dict[str, str] = {
    reason_code: meta["clause"] for reason_code, meta in VIOLATION_CLAUSES.items()
}


# ─── Public API ───────────────────────────────────────────────────────────────


def resolve_clause(reason_code: str) -> dict[str, str] | None:
    """Return the canonical clause meta for a BLOCKED reason_code, or None.

    Callers that produce BLOCKED rows should call this and embed the result
    under `violation_clause_code` in their gate_evidence_json.
    """
    if not reason_code:
        return None
    return VIOLATION_CLAUSES.get(reason_code)


def enrich_blocked_reason(blocked_reason: dict[str, object]) -> dict[str, object]:
    """Add `violation_clause_code` to a BLOCKED reason payload (idempotent).

    The input is expected to carry at least `reason_code` (str). When the
    code is recognized, the returned dict gains:

        violation_clause_code: {clause, name, label_ko}

    Unknown reason_codes pass through unchanged (the caller may emit a
    `violation_clause_code: null` audit row for later catalogue extension).
    """
    if not isinstance(blocked_reason, dict):
        raise TypeError("blocked_reason must be a dict")
    reason_code = blocked_reason.get("reason_code")
    if not isinstance(reason_code, str):
        return blocked_reason
    meta = resolve_clause(reason_code)
    if meta is None:
        return blocked_reason
    enriched = dict(blocked_reason)
    enriched["violation_clause_code"] = meta
    return enriched


def list_clauses() -> list[dict[str, str]]:
    """Return a sorted snapshot of all canonical clause entries."""
    entries: list[dict[str, str]] = []
    for reason_code, meta in VIOLATION_CLAUSES.items():
        entries.append({"reason_code": reason_code, **meta})
    entries.sort(key=lambda e: e["clause"])
    return entries
