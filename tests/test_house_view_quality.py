"""P2-3: house_view AI body carries a data-quality disclosure + faithfulness signal.

Unlike the portfolio/briefing/nba dispatchers, the house_view generator persisted
no grounding signal, so a synthetic AI market view could read as a verified house
view. The service now computes a deterministic faithfulness assessment over the
generated prose (V081 ``faithfulness_json``), and the router attaches the static
synthetic disclosure whenever the row carries AI content.

Deterministic, no DB: exercises the faithfulness-text builder and the router
serialization helper directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.services.ai.output_quality import (  # noqa: E402
    SYNTHETIC_ADVISORY_NOTICE,
)
from apps.api.harness.services.house_view import (  # noqa: E402
    _faithfulness_text,
    attach_house_view_quality,
)


def test_faithfulness_text_joins_prose_excludes_allocations() -> None:
    content = {
        "summary": "거시 총평",
        "asset_views": [{"asset_class": "주식", "rationale": "밸류 +12% 근거"}],
        "risks": ["금리 리스크"],
        "leading_block": {
            "loss_warning": "원금 손실 가능",
            "uncertainty_disclaimer": "불확실성 고지",
        },
        "model_portfolios": [
            {"profile": "성장", "allocation": [{"weight_pct": 65}]}
        ],
    }
    text = _faithfulness_text(content)
    assert "거시 총평" in text
    assert "+12%" in text
    assert "금리 리스크" in text
    assert "원금 손실 가능" in text
    # prescriptive allocation weights are intentionally excluded from the check text
    assert "65" not in text


def test_generated_row_gets_disclosure_and_decoded_faithfulness() -> None:
    row = {
        "ai_generated_at": "2026-05-30T00:00:00Z",
        "faithfulness_json": json.dumps({"method": "deterministic_v1", "passed": True}),
    }
    out = attach_house_view_quality(row)
    assert out["data_quality_notice"] == SYNTHETIC_ADVISORY_NOTICE
    assert isinstance(out["faithfulness"], dict)
    assert out["faithfulness"]["method"] == "deterministic_v1"


def test_draft_without_ai_body_is_untouched() -> None:
    out = attach_house_view_quality({"ai_generated_at": None, "faithfulness_json": None})
    assert "data_quality_notice" not in out
    assert "faithfulness" not in out


def test_malformed_faithfulness_json_decodes_to_none() -> None:
    out = attach_house_view_quality(
        {"ai_generated_at": "2026-05-30T00:00:00Z", "faithfulness_json": "{not json"}
    )
    assert out["faithfulness"] is None
    assert out["data_quality_notice"] == SYNTHETIC_ADVISORY_NOTICE
