"""Faithfulness scoring for RAG QA answers.

Computes token-overlap faithfulness between a generated answer and the
evidence chunks it is grounded in.  Returns a float in [0.0, 1.0].

If DeepEval is installed and the environment variable
``AI_FAITHFULNESS_USE_DEEPEVAL=true`` is set, the scorer delegates to
DeepEval's FaithfulnessMetric (pre-approved under ADR-003 §3).

Threshold: faithfulness >= AI_FAITHFULNESS_MIN (default 0.7) is required
for a READY classification in the RAG QA pipeline (ADR-005 §4).
"""

from __future__ import annotations

import os
import re


# ---------------------------------------------------------------------------
# Tokenisation — Korean-aware
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[가-힣]+|[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Lowercase word-tokenize; Korean syllable blocks are kept whole."""
    return set(_TOKEN_RE.findall(text.lower()))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def faithfulness_min() -> float:
    """Return the configured faithfulness threshold (default 0.7)."""
    raw = os.getenv("AI_FAITHFULNESS_MIN", "0.7").strip()
    try:
        value = float(raw)
    except ValueError:
        return 0.7
    return max(0.0, min(1.0, value))


def is_faithful(score: float) -> bool:
    """Return True when *score* meets the configured threshold."""
    return score >= faithfulness_min()


# ---------------------------------------------------------------------------
# Core scorer
# ---------------------------------------------------------------------------


def compute_faithfulness(answer: str, evidence_chunks: list[str]) -> float:
    """Return token-overlap faithfulness score in [0.0, 1.0].

    Score = |answer_tokens ∩ evidence_tokens| / |answer_tokens|

    A score of 0.0 is returned for empty inputs so callers can treat it as
    an unconditional LOW_FAITHFULNESS signal.

    Args:
        answer: The generated answer text to evaluate.
        evidence_chunks: List of source chunk texts used as grounding.

    Returns:
        Faithfulness score in [0.0, 1.0].
    """
    if not answer.strip() or not evidence_chunks:
        return 0.0

    if os.getenv("AI_FAITHFULNESS_USE_DEEPEVAL", "").strip().lower() in {
        "1", "true", "yes",
    }:
        score = _try_deepeval(answer, evidence_chunks)
        if score is not None:
            return score

    answer_tokens = _tokenize(answer)
    if not answer_tokens:
        return 0.0

    evidence_tokens: set[str] = set()
    for chunk in evidence_chunks:
        evidence_tokens |= _tokenize(chunk)

    if not evidence_tokens:
        return 0.0

    overlap = answer_tokens & evidence_tokens
    return len(overlap) / len(answer_tokens)


# ---------------------------------------------------------------------------
# Optional DeepEval bridge (ADR-003 pre-approved)
# ---------------------------------------------------------------------------


def _try_deepeval(answer: str, evidence_chunks: list[str]) -> float | None:
    """Attempt a DeepEval faithfulness score; return None if unavailable."""
    try:
        from deepeval.metrics import FaithfulnessMetric  # pyright: ignore[reportMissingImports]
        from deepeval.test_case import LLMTestCase  # pyright: ignore[reportMissingImports]

        metric = FaithfulnessMetric(threshold=faithfulness_min())  # pyright: ignore[reportUnknownVariableType]
        test_case = LLMTestCase(  # pyright: ignore[reportUnknownVariableType]
            input="",
            actual_output=answer,
            retrieval_context=evidence_chunks,
        )
        metric.measure(test_case)  # pyright: ignore[reportUnknownMemberType]
        return float(metric.score)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    except Exception:  # noqa: BLE001
        return None
