"""P2-7: recommendation/order simulation responses carry the synthetic data
disclosure + provenance.

A simulation's suitability verdict is computed over synthetic, unverified customer
data (risk grade, total assets). ``_attach_sim_provenance`` stamps the synthetic
disclosure + provenance so a banker does not read the gate result as a verified
fact. Deterministic, no DB.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.api.routers.simulations import (  # noqa: E402
    _attach_sim_provenance,
)
from apps.api.harness.services.ai.output_quality import (  # noqa: E402
    SYNTHETIC_ADVISORY_NOTICE,
)


def test_sim_carries_disclosure_and_provenance() -> None:
    out = _attach_sim_provenance({"id": "x", "status_code": "APPROVED"})
    assert out["data_quality_notice"] == SYNTHETIC_ADVISORY_NOTICE
    prov = out["data_provenance"]
    assert prov["display_basis_code"] == "SYNTHETIC_HOLDING_VALUE"
    assert prov["freshness_status_code"] == "MISSING"
    assert prov["quality_status_code"] == "UNVERIFIED"


def test_sim_disclosure_applies_to_blocked_verdict_too() -> None:
    # a BLOCKED suitability verdict is still synthetic-data-derived and must disclose
    out = _attach_sim_provenance({"id": "y", "status_code": "BLOCKED"})
    assert "data_quality_notice" in out
    assert "data_provenance" in out
