"""P2-4 / P2-5: consultation_briefing & nba_script carry a per-customer data
provenance, and nba_script's faithfulness gate matches portfolio/briefing.

P2-4: ``synthetic_portfolio_provenance`` is a disclosure-only projection of the
valuation basis (display_basis / freshness / quality + message) — the structured
provenance the briefing/nba outputs lacked relative to portfolio_analysis, without
a misleading holding total.

P2-5: nba_script appends the synthetic notice to the faithfulness ASSESSED text
(not the persisted, customer-facing script_text) and runs require_disclosure=True,
matching portfolio_analysis/consultation_briefing — so disclosure presence is
flagged consistently without polluting the talking-point script.

Deterministic, no DB.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.services.ai.output_quality import (  # noqa: E402
    SYNTHETIC_ADVISORY_NOTICE,
    assess_faithfulness,
)
from apps.api.harness.services.readiness.core import (  # noqa: E402
    synthetic_portfolio_provenance,
)

_REQUIRED_KEYS = {"display_basis_code", "freshness_status_code", "quality_status_code"}


def test_provenance_has_required_disclosure_keys() -> None:
    prov = synthetic_portfolio_provenance()
    assert _REQUIRED_KEYS.issubset(prov.keys())
    assert prov["display_basis_code"] == "SYNTHETIC_HOLDING_VALUE"
    assert prov["freshness_status_code"] == "MISSING"
    assert prov["quality_status_code"] == "UNVERIFIED"


def test_provenance_omits_misleading_holding_total() -> None:
    # briefing/nba do not surface holding totals; the projection must not claim one.
    prov = synthetic_portfolio_provenance()
    assert "total_market_value_krw" not in prov


def test_provenance_keys_stable_with_or_without_portfolios() -> None:
    empty = synthetic_portfolio_provenance()
    with_pf = synthetic_portfolio_provenance(
        portfolios=[{"id": "p1"}], holdings=[{"market_value_krw": 1000, "as_of_date": "2026-01-01"}]
    )
    assert empty["display_basis_code"] == with_pf["display_basis_code"]
    assert empty["quality_status_code"] == with_pf["quality_status_code"]


def test_nba_faithfulness_disclosure_in_assessed_text_not_script() -> None:
    """P2-5 mechanism: the notice appended to the assessed text satisfies
    require_disclosure=True even though the talking-point script omits it."""
    script_text = "안녕하세요 고객님, 포트폴리오 점검을 제안드립니다."
    # script alone (require_disclosure=True) would flag a missing disclosure
    bare = assess_faithfulness(
        output_text=script_text, model_input={"x": 1}, require_disclosure=True
    )
    assert "MISSING_DATA_QUALITY_DISCLOSURE" in bare["flags"]
    # appending the carried notice (what nba_script now does) clears the flag
    assessed = assess_faithfulness(
        output_text=script_text + "\n" + SYNTHETIC_ADVISORY_NOTICE,
        model_input={"x": 1},
        require_disclosure=True,
    )
    assert "MISSING_DATA_QUALITY_DISCLOSURE" not in assessed["flags"]
    assert assessed["has_disclosure"] is True
