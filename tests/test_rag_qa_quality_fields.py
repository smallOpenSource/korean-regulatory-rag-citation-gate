"""P2-2: every RAG QA reply carries a data-quality disclosure + faithfulness signal.

POST /rag/qa returned AI-derived text to a banker with no data-quality disclosure
and no grounding signal. ``_rag_quality_fields`` is mixed into every READY and
BLOCKED reply so the response always exposes the synthetic disclosure plus a
deterministic faithfulness assessment of the answer against its citations.

Deterministic, no DB: exercises the response-field builder directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.api.routers.ai import (  # noqa: E402
    SYNTHETIC_ADVISORY_NOTICE,
    _rag_quality_fields,
)


def test_blocked_reply_has_both_quality_keys() -> None:
    fields = _rag_quality_fields(None, [])
    assert fields["data_quality_notice"] == SYNTHETIC_ADVISORY_NOTICE
    assert fields["faithfulness"]["method"] == "deterministic_v1"


def test_ready_reply_has_both_quality_keys() -> None:
    fields = _rag_quality_fields("근거 기반 답변", [{"quote": "출처 텍스트"}])
    assert "data_quality_notice" in fields
    assert fields["faithfulness"]["method"] is not None


def test_answer_figure_grounded_in_citation_not_flagged() -> None:
    answer = "평가액은 720,000,000원입니다"
    citations = [{"quote": "기준 평가액 720,000,000원"}]
    fields = _rag_quality_fields(answer, citations)
    assert fields["faithfulness"]["ungrounded_figures"] == []


def test_answer_figure_absent_from_citation_flagged() -> None:
    answer = "향후 수익률 +37.7% 전망"
    citations = [{"quote": "시장 동향 일반 서술"}]
    fields = _rag_quality_fields(answer, citations)
    assert "UNGROUNDED_FIGURES" in fields["faithfulness"]["flags"]
