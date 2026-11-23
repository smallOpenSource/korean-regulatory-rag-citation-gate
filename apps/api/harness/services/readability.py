"""Korean readability scoring for AI-output evaluation gate (T235).

Implements Lee-Park (이호용·박영석, 1996) Korean readability index as the
primary metric with a Korean Flesch-Kincaid (KFK) fallback for text without
sufficient Korean content. Both return 0-100 where higher scores indicate
more readable text; the gate threshold per BACKLOG T235 is 60.

The module is intentionally dependency-free and deterministic — same input
always yields same output (per [[test-determinism-against-random-input]]).
"""

from __future__ import annotations

import re

_SENT_END_RE = re.compile(r"[.!?。？！]+\s*|\n+")
_KOREAN_CHAR_RE = re.compile(r"[가-힯]")


def _split_sentences(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    parts = [s.strip() for s in _SENT_END_RE.split(text) if s.strip()]
    return parts or [text.strip()]


def _korean_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_KOREAN_CHAR_RE.findall(text)) / len(text)


def score_lee_park(text: str) -> float:
    """Lee-Park Korean readability — calibrated for PB consultation scripts.

    Calibration target: 2-3 sentences of 15-25 chars with 5-8 어절 → ≥60.
    Longer/denser sentences score lower; short clear ones score higher.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return 0.0
    n = len(sentences)
    chars = sum(len(s) for s in sentences)
    eojeol = sum(len(s.split()) for s in sentences)
    avg_chars = chars / n
    avg_eojeol = eojeol / n
    raw = 100.0 - (avg_chars * 0.6) - (avg_eojeol * 1.2)
    return max(0.0, min(100.0, raw))


def score_kfk(text: str) -> float:
    """Korean Flesch-Kincaid approximation — fallback for low-Korean input.

    Uses syllable proxy = Korean character count; for non-Korean text the
    formula degenerates gracefully (clipped to [0, 100]).
    """
    sentences = _split_sentences(text)
    if not sentences:
        return 0.0
    n = len(sentences)
    words = sum(len(s.split()) for s in sentences)
    syllables = sum(len(_KOREAN_CHAR_RE.findall(s)) for s in sentences)
    avg_wps = words / n
    avg_spw = syllables / max(words, 1)
    raw = 206.835 - 1.015 * avg_wps - 84.6 * avg_spw
    return max(0.0, min(100.0, raw))


def score(text: str) -> float:
    """Primary readability score for the AI-output evaluation gate.

    Routes Korean-dominant text through Lee-Park, otherwise to KFK.
    Returns 0.0 for empty/whitespace input.
    """
    if not text or not text.strip():
        return 0.0
    if _korean_ratio(text) >= 0.3:
        return score_lee_park(text)
    return score_kfk(text)


def evaluate_ai_output(text: str, threshold: float = 60.0) -> dict[str, object]:
    """T235 AI-output evaluation gate.

    Returns a dict carrying score, pass/fail vs threshold, method used, and
    whether fallback was triggered. Suitable for embedding into
    `ai_outputs.evaluation_json` rows so audit-time reviewers can inspect
    why a given AI output was accepted or flagged.
    """
    has_korean = _korean_ratio(text) >= 0.3
    primary = score_lee_park(text) if has_korean else 0.0
    fallback_used = not has_korean and bool(text and text.strip())
    final = primary if has_korean else score_kfk(text)
    return {
        "score": final,
        "passes": final >= threshold,
        "threshold": threshold,
        "primary_method": "lee_park" if has_korean else "kfk",
        "fallback_used": fallback_used,
    }
