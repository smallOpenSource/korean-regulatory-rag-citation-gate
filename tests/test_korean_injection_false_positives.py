"""False-positive test suite — 14 PI-KO patterns × Korean compliance corpus (AC22).

Verifies that all 14 PI-KO regex patterns produce zero spurious matches
against the negative corpus of normal PB/WM domain text in Korean.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

YAML_PATH = Path(__file__).parent.parent / "prompts" / "INJECTION_PATTERNS.yaml"
CORPUS_PATH = Path(__file__).parent / "fixtures" / "korean_compliance_corpus.txt"

# Seed SQL sentences (lines 24-28: doc_no 1-5 raw_text values)
SEED_SQL_SENTENCES: list[str] = [
    "상담 완료 전 적합성 확인, 설명 확인, 직원 최종 승인이 모두 필요하다.",
    "사후관리는 만기, knock-in, 평가손실, 정기 리뷰, 장기 미접촉 사례를 추적한다.",
    "시장 데이터는 실제 공급자 수집기에서만 저장하며, 자격증명 누락은 SKIPPED 또는 FAILED 배치 로그로 남긴다.",
    "수동 기준 문서 청크는 임베딩 대기 상태로 시작하며 내부 BGE refresh 이후 검색 준비 상태가 된다.",
    "권유 시뮬레이션 승인은 적합성, 설명 확인, 교육용 고객 동의, 직원 최종 승인을 모두 요구한다.",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ko_patterns() -> list[dict]:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    return [
        p for p in data["patterns"]
        if str(p.get("id", "")).startswith("PI-KO-")
    ]


@pytest.fixture(scope="module")
def negative_corpus() -> list[str]:
    """Combined corpus: seed SQL sentences + corpus file lines (non-comment, non-empty)."""
    lines: list[str] = list(SEED_SQL_SENTENCES)
    if CORPUS_PATH.exists():
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
    return lines


# ---------------------------------------------------------------------------
# Core AC22 test
# ---------------------------------------------------------------------------


def test_corpus_file_exists():
    assert CORPUS_PATH.exists(), f"Corpus file not found: {CORPUS_PATH}"


def test_corpus_has_sufficient_entries(negative_corpus: list[str]):
    assert len(negative_corpus) >= 50, (
        f"Corpus should have >= 50 entries, got {len(negative_corpus)}"
    )


def test_14_ko_patterns_loaded(ko_patterns: list[dict]):
    assert len(ko_patterns) == 14, (
        f"Expected 14 PI-KO patterns, got {len(ko_patterns)}"
    )


@pytest.mark.parametrize("pattern_entry", [
    pytest.param({"id": f"PI-KO-{i:03d}"}, id=f"PI-KO-{i:03d}")
    for i in range(1, 15)
])
def test_no_false_positives_per_pattern(
    pattern_entry: dict,
    ko_patterns: list[dict],
    negative_corpus: list[str],
):
    """Each PI-KO pattern must produce 0 matches against the negative corpus."""
    pid = pattern_entry["id"]
    pattern = next((p for p in ko_patterns if p["id"] == pid), None)
    assert pattern is not None, f"{pid} not found in INJECTION_PATTERNS.yaml"

    regex = pattern["regex"]
    spurious: list[tuple[str, str]] = []
    for sentence in negative_corpus:
        try:
            if re.search(regex, sentence):
                spurious.append((pid, sentence))
        except re.error as exc:
            pytest.fail(f"{pid} regex compile error: {exc}")

    assert not spurious, (
        f"PI-KO false positives detected ({len(spurious)} matches):\n"
        + "\n".join(f"  [{p}] {s!r}" for p, s in spurious)
    )


# ---------------------------------------------------------------------------
# Seed SQL sentence spot-checks (lines 24-28 of seed_40_manual_rag.sql)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", SEED_SQL_SENTENCES)
def test_seed_sql_sentence_no_ko_match(sentence: str, ko_patterns: list[dict]):
    """Each seed_40_manual_rag.sql sentence must not trigger any PI-KO pattern."""
    for pattern in ko_patterns:
        pid = pattern["id"]
        regex = pattern["regex"]
        try:
            match = re.search(regex, sentence)
        except re.error:
            continue
        assert match is None, (
            f"Seed sentence matched {pid} (false positive):\n"
            f"  sentence: {sentence!r}\n"
            f"  regex:    {regex!r}\n"
            f"  match:    {match.group(0)!r}"
        )
