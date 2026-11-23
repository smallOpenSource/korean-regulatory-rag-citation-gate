"""Stage 3 T235 — readability score + AI-output evaluation gate."""

from __future__ import annotations

from apps.api.harness.services.readability import (
    evaluate_ai_output,
    score,
    score_kfk,
    score_lee_park,
)


def test_score_empty_returns_zero():
    assert score("") == 0.0
    assert score("   \n\t  ") == 0.0


def test_score_test_returns_non_negative():
    """v6 plan §5 Stage 3 explicit gate: assert score('test') >= 0."""
    assert score("test") >= 0.0


def test_score_short_clear_korean_passes_threshold():
    text = "오늘 시장은 안정적입니다. 위험은 낮습니다. 추천을 따르세요."
    assert score(text) >= 60.0


def test_score_long_dense_korean_fails_threshold():
    text = (
        "오늘 시장은 매우 복잡한 양상을 보이고 있으며 다양한 거시경제 변수들이 "
        "동시에 작용하여 단기 예측이 매우 어려운 상황으로 평가되고 있습니다."
    )
    assert score(text) < 60.0


def test_evaluate_returns_full_payload():
    result = evaluate_ai_output("짧은 문장입니다.")
    assert set(result.keys()) == {
        "score",
        "passes",
        "threshold",
        "primary_method",
        "fallback_used",
    }
    assert result["threshold"] == 60.0
    assert isinstance(result["passes"], bool)
    assert isinstance(result["score"], float)


def test_evaluate_custom_threshold():
    result = evaluate_ai_output("test", threshold=10.0)
    assert result["threshold"] == 10.0


def test_evaluate_korean_uses_lee_park():
    result = evaluate_ai_output("이 문장은 충분히 짧고 명확합니다.")
    assert result["primary_method"] == "lee_park"
    assert result["fallback_used"] is False


def test_evaluate_english_uses_kfk_fallback():
    result = evaluate_ai_output("Hello world test sentence")
    assert result["primary_method"] == "kfk"
    assert result["fallback_used"] is True
    assert result["score"] >= 0.0


def test_score_is_deterministic_across_repeated_calls():
    """Per memory rule [[test-determinism-against-random-input]] — same
    input must yield identical output every call (no random state)."""
    text = "테스트 문장입니다. 두 번째 문장입니다."
    runs = {score(text) for _ in range(50)}
    assert len(runs) == 1, f"non-deterministic score: {runs}"


def test_score_is_bounded_0_to_100():
    """Score must stay in [0, 100] for any input."""
    inputs = [
        "",
        "x",
        "한 글자",
        "a " * 500,  # very long English
        "가" * 500,  # very long Korean
        "ABCDEFG",
    ]
    for text in inputs:
        s = score(text)
        assert 0.0 <= s <= 100.0, f"out of bounds for {text!r}: {s}"


def test_score_lee_park_directly_callable():
    """Lee-Park primary scorer should also be importable + callable."""
    assert score_lee_park("짧은 문장.") >= 0.0
    assert score_lee_park("") == 0.0


def test_score_kfk_directly_callable():
    """KFK fallback scorer should also be importable + callable."""
    assert score_kfk("short") >= 0.0
    assert score_kfk("") == 0.0
