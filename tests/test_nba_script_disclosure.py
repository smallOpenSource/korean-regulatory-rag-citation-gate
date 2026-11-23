"""P2-1: NBA list/detail script_text carries the synthetic data-quality disclosure.

The nba_script dispatcher stamps ``data_quality_notice`` + faithfulness onto
``ai_outputs``, but the NBA routes return ``script_text`` straight from
``nba_actions`` — a path that bypassed that disclosure (silent-synthetic). The
router serialization helper ``_attach_script_disclosure`` closes that gap: every
script-bearing NBA response item must carry ``SYNTHETIC_ADVISORY_NOTICE`` so a
banker never reads a synthetic/unverified script as a verified talking-point.

Deterministic, no DB: exercises the serialization invariant directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.api.routers.nba import (  # noqa: E402
    SYNTHETIC_ADVISORY_NOTICE,
    _attach_script_disclosure,
)
from apps.api.harness.services.ai.output_quality import has_disclosure  # noqa: E402


def test_script_text_present_gets_disclosure() -> None:
    item = _attach_script_disclosure({"id": "x", "script_text": "포트폴리오 점검 제안 스크립트"})
    assert item["script_disclosure"] == SYNTHETIC_ADVISORY_NOTICE


def test_no_script_text_no_disclosure() -> None:
    for empty in (None, "", 0):
        item = _attach_script_disclosure({"id": "x", "script_text": empty})
        assert "script_disclosure" not in item, f"unexpected disclosure for script_text={empty!r}"
    missing = _attach_script_disclosure({"id": "x"})
    assert "script_disclosure" not in missing


def test_list_invariant_every_script_bearing_item_disclosed() -> None:
    """The GET /nba-actions acceptance: (script_text != null) AND (no script_disclosure) == 0."""
    items = [
        {"id": "1", "script_text": "스크립트 A"},
        {"id": "2", "script_text": None},
        {"id": "3", "script_text": "스크립트 C"},
        {"id": "4"},
    ]
    serialized = [_attach_script_disclosure(i) for i in items]
    offenders = [i for i in serialized if i.get("script_text") and "script_disclosure" not in i]
    assert offenders == []


def test_disclosure_is_recognised_by_faithfulness_gate() -> None:
    """The attached notice must register as a disclosure for the deterministic gate,
    so the list-path signal and the dispatcher gate speak the same language."""
    assert has_disclosure(SYNTHETIC_ADVISORY_NOTICE) is True
