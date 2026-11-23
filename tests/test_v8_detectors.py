"""test_v8_detectors.py — Stage 2 G2 deliverable (T111)

Deterministic detector unit tests for L1/L3/L4.
50× determinism repeat per fixture (test-determinism-against-random-input).

L1 BANNED regex: 10 patterns × {match, no-match} = 20 cases
L3 format consistency: timestamp/currency/honorific × {valid, invalid}
L4 cross-field: 12 known combos × {valid, invalid}
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

SCRIPTS_DIR = (pathlib.Path(__file__).resolve().parents[1] / "scripts")
sys.path.insert(0, str(SCRIPTS_DIR))

from v8_detector_L1_banned_regex import scan_l1  # noqa: E402
from v8_detector_L3_format_consistency import scan_l3  # noqa: E402
from v8_detector_L4_cross_field import L4_COMBOS, scan_l4  # noqa: E402

DETERMINISM_REPEAT = 50


# --------------------------------------------------------------------------
# L1 BANNED regex tests — 10 patterns × {match, no-match}
# --------------------------------------------------------------------------

L1_FIXTURES_MATCH = [
    ("BANNED_ENGLISH", "evidence based decision"),
    ("BANNED_INTERNAL_ID", "see ADR-009 for context"),
    ("BANNED_TEST_FIXTURE", "GOLDEN_TEST baseline"),
    ("BANNED_ISO_MICRO", "at 2026-05-19T13:52:53.650391"),
    ("BANNED_PG_MICRO_TIMESTAMP", "2026-05-16 14:52:16.847752"),
    ("BANNED_PG_SHORT_TZ", "14:52:16.847752+00"),
    ("BANNED_PLACEHOLDER", "응답을 기다리는 중"),
    ("BANNED_RAW_DB_FIELD", "field source_as_of is set"),
    ("BANNED_AUDIT_PREFIX", "AUDIT-NEG-001 leaked"),
    ("BANNED_DASH", "정보: — 미확인"),
]

L1_FIXTURES_NOMATCH = [
    "고객님께서 자산 현황을 확인하셨습니다.",
    "2026년 5월 20일 13시 00분 기준",
    "총 1,234,567원 입금 완료",
    "PB님 응답이 도착했습니다.",
]


@pytest.mark.parametrize("pattern,text", L1_FIXTURES_MATCH)
def test_l1_match_deterministic(pattern: str, text: str) -> None:
    results: set[tuple[str, int]] = set()
    for _ in range(DETERMINISM_REPEAT):
        findings = scan_l1(text)
        sig = tuple(sorted((f.pattern_name, f.offset) for f in findings))
        results.add(sig)
    assert len(results) == 1, f"L1 non-deterministic for {pattern}: {results}"
    pattern_names = {p for p, _ in next(iter(results))}
    assert pattern in pattern_names, f"L1 did not match expected {pattern} for {text!r}"


@pytest.mark.parametrize("text", L1_FIXTURES_NOMATCH)
def test_l1_nomatch_deterministic(text: str) -> None:
    for _ in range(DETERMINISM_REPEAT):
        findings = scan_l1(text)
        assert findings == [], f"L1 false positive for {text!r}: {findings}"


# --------------------------------------------------------------------------
# L3 format consistency tests
# --------------------------------------------------------------------------

L3_FIXTURES_MATCH = [
    ("honorific", "PB씨가 입금"),
    ("currency", "ADMIN님 12345원 처리"),
    ("currency", "총 1,234,567 (단위 누락)"),
]

L3_FIXTURES_NOMATCH = [
    "PB님께서 2026-05-20 13:00에 1,234,567원을 입금하셨습니다.",
    "고객님께 안내드립니다.",
]


@pytest.mark.parametrize("category,text", L3_FIXTURES_MATCH)
def test_l3_match_deterministic(category: str, text: str) -> None:
    results: set[tuple[str, ...]] = set()
    for _ in range(DETERMINISM_REPEAT):
        findings = scan_l3(text)
        sig = tuple(sorted(f.pattern_name for f in findings))
        results.add(sig)
    assert len(results) == 1, f"L3 non-deterministic for {text!r}: {results}"
    cats = {f.category for f in scan_l3(text)}
    assert category in cats, f"L3 expected {category} for {text!r}, got {cats}"


@pytest.mark.parametrize("text", L3_FIXTURES_NOMATCH)
def test_l3_nomatch_deterministic(text: str) -> None:
    for _ in range(DETERMINISM_REPEAT):
        findings = scan_l3(text)
        assert findings == [], f"L3 false positive for {text!r}: {findings}"


# --------------------------------------------------------------------------
# L4 cross-field tests — 12 combos
# --------------------------------------------------------------------------

L4_FIXTURES_MATCH = [
    ("L4-01", {"ai_generated_at": "2026-05-20", "ai_payload": None}),
    ("L4-02", {"entity": "consultations", "status": "COMPLETED"}),
    ("L4-03", {"entity": "email_drafts", "status": "SENT"}),
    ("L4-04", {"entity": "email_drafts", "status": "FAILED", "error_message": None}),
    ("L4-05", {"entity": "house_views", "status": "ACTIVE"}),
    ("L4-06", {"entity": "house_views", "status": "SUPERSEDED"}),
    ("L4-07", {"entity": "aftercare_events", "status": "RESOLVED"}),
    ("L4-08", {"entity": "nba_actions", "status": "SNOOZED"}),
    ("L4-09", {"entity": "email_drafts", "status": "APPROVED"}),
    ("L4-10", {"entity": "batch_jobs", "status": "RUNNING", "progress_pct": 100}),
    ("L4-11", {"entity": "batch_jobs", "status": "DONE", "progress_pct": 80}),
    ("L4-12", {"status": "CANCELLED", "due_at": "9999-01-01", "now": "2026-05-20"}),
]

L4_FIXTURES_NOMATCH = [
    {"entity": "consultations", "status": "COMPLETED", "summary": "상담 완료"},
    {"entity": "email_drafts", "status": "SENT", "message_id": "msg-001"},
    {"entity": "batch_jobs", "status": "DONE", "progress_pct": 100},
    {"status": "DRAFT"},
]


@pytest.mark.parametrize("combo_prefix,fields", L4_FIXTURES_MATCH)
def test_l4_match_deterministic(combo_prefix: str, fields: dict) -> None:
    results: set[tuple[str, ...]] = set()
    for _ in range(DETERMINISM_REPEAT):
        findings = scan_l4(fields)
        sig = tuple(sorted(f.combo_id for f in findings))
        results.add(sig)
    assert len(results) == 1, (
        f"L4 non-deterministic for {combo_prefix}: {results}"
    )
    combo_ids = {f.combo_id for f in scan_l4(fields)}
    matching = [cid for cid in combo_ids if cid.startswith(combo_prefix)]
    assert matching, f"L4 expected {combo_prefix} for {fields}, got {combo_ids}"


@pytest.mark.parametrize("fields", L4_FIXTURES_NOMATCH)
def test_l4_nomatch_deterministic(fields: dict) -> None:
    for _ in range(DETERMINISM_REPEAT):
        findings = scan_l4(fields)
        assert findings == [], f"L4 false positive for {fields}: {findings}"


def test_l4_combo_total_is_12() -> None:
    assert len(L4_COMBOS) == 12, f"L4 combo catalog must have 12 entries, got {len(L4_COMBOS)}"


def test_l4_combo_ids_unique() -> None:
    ids = [c.combo_id for c in L4_COMBOS]
    assert len(ids) == len(set(ids)), f"L4 combo_ids not unique: {ids}"
