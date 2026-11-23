"""Stage 3 T213 — 금소법 §57/§69 violation_clause_code mapping."""

from __future__ import annotations

import pytest

from apps.api.harness.services.compliance.violation_clause import (
    CLAUSE_BY_REASON,
    VIOLATION_CLAUSES,
    enrich_blocked_reason,
    list_clauses,
    resolve_clause,
)


def test_catalogue_has_eleven_clauses():
    """All §17/§18/§19/§20/§21/§22/§23/§28/§44/§45/§47 canonicalized."""
    assert len(VIOLATION_CLAUSES) == 11
    clauses = {meta["clause"] for meta in VIOLATION_CLAUSES.values()}
    assert clauses == {"§17", "§18", "§19", "§20", "§21", "§22", "§23", "§28", "§44", "§45", "§47"}


def test_resolve_clause_known_returns_meta():
    meta = resolve_clause("SUITABILITY_FAILED")
    assert meta is not None
    assert meta["clause"] == "§17"
    assert meta["name"] == "suitability_principle"
    assert meta["label_ko"] == "적합성 원칙 위반"


def test_resolve_clause_unknown_returns_none():
    assert resolve_clause("UNKNOWN_REASON") is None
    assert resolve_clause("") is None


def test_enrich_blocked_reason_adds_field():
    payload = {"reason_code": "EXPLANATION_FAILED", "detail": "no AI footer"}
    enriched = enrich_blocked_reason(payload)
    assert enriched["reason_code"] == "EXPLANATION_FAILED"
    assert enriched["detail"] == "no AI footer"
    assert enriched["violation_clause_code"]["clause"] == "§19"


def test_enrich_blocked_reason_does_not_mutate_input():
    payload = {"reason_code": "EXPLANATION_FAILED"}
    enrich_blocked_reason(payload)
    assert "violation_clause_code" not in payload


def test_enrich_blocked_reason_idempotent():
    payload = {"reason_code": "UNFAIR_PRACTICE_DETECTED"}
    a = enrich_blocked_reason(payload)
    b = enrich_blocked_reason(a)
    assert a == b


def test_enrich_unknown_reason_passes_through():
    payload = {"reason_code": "NOT_IN_CATALOGUE"}
    result = enrich_blocked_reason(payload)
    assert "violation_clause_code" not in result


def test_enrich_missing_reason_code_passes_through():
    payload = {"detail": "no reason_code field"}
    result = enrich_blocked_reason(payload)
    assert result == payload


def test_enrich_rejects_non_dict():
    with pytest.raises(TypeError):
        enrich_blocked_reason("not a dict")  # type: ignore[arg-type]


def test_clause_by_reason_consistency():
    """CLAUSE_BY_REASON shortcut must match VIOLATION_CLAUSES content."""
    for reason_code, expected_clause in CLAUSE_BY_REASON.items():
        assert VIOLATION_CLAUSES[reason_code]["clause"] == expected_clause


def test_list_clauses_returns_sorted_snapshot():
    entries = list_clauses()
    assert len(entries) == 11
    clauses = [e["clause"] for e in entries]
    assert clauses == sorted(clauses, key=lambda c: int(c.lstrip("§")))


def test_list_clauses_contains_reason_code():
    entries = list_clauses()
    for entry in entries:
        assert "reason_code" in entry
        assert "clause" in entry
        assert "name" in entry
        assert "label_ko" in entry
