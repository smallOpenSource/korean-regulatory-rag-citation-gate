"""v8 state_hash determinism tests — PRD §11.7 + DELTA-N2.

50× repeat (per fixture) × 5 fixtures = 250 calls.
Each fixture's hash set must have length 1 (perfect determinism).

Cross-ref: [[test-determinism-against-random-input]] strict 50× repeat.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts/ to path for state_hash import.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from v8_state_hash import Cell, state_hash, canonicalize  # noqa: E402


# 5 representative fixtures covering different content states + interactions + visible text patterns.
FIXTURES: list[Cell] = [
    Cell(
        route_pattern="/customers/:customerId",
        role="PB",
        content_state="customers#LOADED",
        interaction_state="click",
        visible_text="고객 김민준 - 자산 5억원 - 2026-05-20T13:25:00.123456Z",
    ),
    Cell(
        route_pattern="/house-views/:houseViewId",
        role="WM",
        content_state="house_views#GENERATED",
        interaction_state="keyboard",
        visible_text="2026 H1 자산전망 — 발행일 2026-05-20 09:30:00.847752+09",
    ),
    Cell(
        route_pattern="/nba",
        role="PB",
        content_state="nba_actions#PENDING",
        interaction_state="modal",
        visible_text="P1 next-best-action: 김민준 / 7d6b9a12-3c4d-4e5f-9012-3456789abcde",
    ),
    Cell(
        route_pattern="/dashboard",
        role="ADMIN",
        content_state="dashboard#LOADED",
        interaction_state="aria-live",
        visible_text="감사 로그 신규 12건  ·  2026-05-20  ·  data-testid=\"badge\"",
    ),
    Cell(
        route_pattern="/audit",
        role="AUDIT_VIEWER",
        content_state="audit_logs#FILTERED",
        interaction_state="form-state",
        visible_text="조회 결과 47건 / 페이지 1 / 정렬: created_at DESC",
    ),
]


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda c: f"{c.role}@{c.route_pattern}")
def test_state_hash_50x_determinism(fixture: Cell) -> None:
    """Each fixture must produce the identical hash across 50 consecutive calls."""
    hashes = {state_hash(fixture) for _ in range(50)}
    assert len(hashes) == 1, (
        f"determinism violation for {fixture.route_pattern} @ {fixture.role}: "
        f"{len(hashes)} distinct hashes across 50 calls"
    )


def test_canonical_form_strips_timestamp_microseconds() -> None:
    """ISO + PG timestamps lose seconds/microseconds → cycle 0/1 hash stability."""
    a = Cell("/x", "PB", "x#A", "click", "t=2026-05-20T13:25:00.123456Z")
    b = Cell("/x", "PB", "x#A", "click", "t=2026-05-20T13:25:00.999999Z")
    assert state_hash(a) == state_hash(b)


def test_canonical_form_normalizes_uuid() -> None:
    """Raw UUIDs collapse to a stable resource-type token under default map."""
    a = Cell("/x", "PB", "x#A", "click", "id=7d6b9a12-3c4d-4e5f-9012-3456789abcde")
    b = Cell("/x", "PB", "x#A", "click", "id=ffeeddcc-bbaa-9988-7766-554433221100")
    assert state_hash(a) == state_hash(b)


def test_canonical_form_strips_data_attributes() -> None:
    """data-* attributes ignored — UI test fixture markers don't perturb hash."""
    a = Cell("/x", "PB", "x#A", "click", '<div data-testid="foo">동일</div>')
    b = Cell("/x", "PB", "x#A", "click", '<div data-testid="bar">동일</div>')
    assert state_hash(a) == state_hash(b)


def test_canonical_form_collapses_whitespace() -> None:
    """Multiple whitespace → single space."""
    a = Cell("/x", "PB", "x#A", "click", "고객   김민준  -  자산")
    b = Cell("/x", "PB", "x#A", "click", "고객 김민준 - 자산")
    assert state_hash(a) == state_hash(b)


def test_canonical_form_korean_nfc_normalize() -> None:
    """Combined vs decomposed Hangul collapses to NFC."""
    nfc = "한글"
    nfd = "한글"  # decomposed
    assert state_hash(Cell("/x", "PB", "x#A", "click", nfc)) == state_hash(
        Cell("/x", "PB", "x#A", "click", nfd)
    )


def test_distinct_inputs_yield_distinct_hashes() -> None:
    """Different role on same cell must produce different hash (safety check)."""
    a = Cell("/x", "PB", "x#A", "click", "동일 텍스트")
    b = Cell("/x", "WM", "x#A", "click", "동일 텍스트")
    assert state_hash(a) != state_hash(b)


def test_canonical_output_format_uses_unit_separator() -> None:
    """5-tuple separator is U+001F (ASCII 0x1F) to avoid colliding with visible text."""
    canon = canonicalize(Cell("/x", "PB", "x#A", "click", "txt"))
    assert canon.count("\x1f") == 4
