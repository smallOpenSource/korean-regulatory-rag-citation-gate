"""Stage 3 T205 — recommendation reasoning lint (금소법 §20)."""

from __future__ import annotations

from apps.api.harness.services.compliance.reasoning_lint import (
    CATEGORY_MAP,
    is_clean,
    lint_reasoning,
)


def test_empty_text_is_clean():
    result = lint_reasoning("")
    assert result["flagged"] is False
    assert result["violations"] == []
    assert result["severity_total"] == 0
    assert result["audit_action_code"] == ""


def test_neutral_recommendation_is_clean():
    text = "이 상품은 고객님의 위험성향에 부합한다고 판단됩니다. 검토 후 결정하시기 바랍니다."
    assert is_clean(text) is True
    assert lint_reasoning(text)["severity_total"] == 0


def test_bundling_flagged():
    text = "다른 상품과 함께 가입하시면 우대 혜택이 있습니다."
    result = lint_reasoning(text)
    assert result["flagged"] is True
    assert result["category_counts"]["bundling"] == 1
    assert result["audit_action_code"] == "unfair_practice_flagged"


def test_coercion_flagged():
    text = "이번 분기에 반드시 가입하셔야 합니다."
    result = lint_reasoning(text)
    assert result["flagged"] is True
    assert result["category_counts"]["coercion"] == 1


def test_aggressive_flagged():
    text = "오늘만 우대 금리가 적용됩니다. 빨리 결정하시는 게 좋습니다."
    result = lint_reasoning(text)
    assert result["flagged"] is True
    assert result["category_counts"]["aggressive"] >= 1


def test_multi_category_hits_accumulate_severity():
    text = "반드시 가입하셔야 하며, 빨리 결정해 주세요. 같이 가입 시 우대됩니다."
    result = lint_reasoning(text)
    assert result["flagged"] is True
    assert result["category_counts"]["coercion"] >= 1
    assert result["category_counts"]["aggressive"] >= 1
    assert result["category_counts"]["bundling"] >= 1
    # 3 + 2 + 2 minimum
    assert result["severity_total"] >= 7


def test_violation_positions_correct():
    text = "고객님, 끼워팔기는 절대 권유하지 않습니다."
    result = lint_reasoning(text)
    assert len(result["violations"]) == 1
    v = result["violations"][0]
    assert v["keyword"] == "끼워팔기"
    assert v["category"] == "bundling"
    assert text[v["position"]:v["position"] + len("끼워팔기")] == "끼워팔기"


def test_repeated_keyword_counted_each_occurrence():
    text = "반드시 가입하셔야 합니다. 반드시 가입은 의무 가입입니다."
    result = lint_reasoning(text)
    coercion = result["category_counts"]["coercion"]
    # 반드시 가입 ×2 + 의무 가입 ×1
    assert coercion >= 3


def test_deterministic_across_repeated_calls():
    """Per [[test-determinism-against-random-input]] — no random state."""
    text = "반드시 가입, 빨리 결정, 같이 가입"
    runs = []
    for _ in range(50):
        r = lint_reasoning(text)
        runs.append((r["flagged"], r["severity_total"], len(r["violations"])))
    assert len(set(runs)) == 1


def test_category_map_has_three_categories():
    assert set(CATEGORY_MAP) == {"bundling", "coercion", "aggressive"}
    for keywords in CATEGORY_MAP.values():
        assert len(keywords) > 0
        for kw, sev in keywords:
            assert isinstance(kw, str)
            assert 1 <= sev <= 3


def test_audit_action_code_only_when_flagged():
    assert lint_reasoning("")["audit_action_code"] == ""
    assert lint_reasoning("normal text")["audit_action_code"] == ""
    assert lint_reasoning("반드시 가입")["audit_action_code"] == "unfair_practice_flagged"
