#!/usr/bin/env python
"""v8_detector_L3_format_consistency.py — Stage 2 G2 deliverable (T104)

L3 format consistency detector. Deterministic regex (no LLM).
Targets: timestamp (KST formatted), currency (KRW), 호칭 (PB/WM titles).

Per PRD §4 #10 catalog reference. PASS = matches expected format.
FAIL = format violation. Deterministic — no LLM dependency.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any

# --- timestamp format expectations (KST, no microseconds) ---
# Acceptable: "YYYY-MM-DD HH:MM" or "YYYY-MM-DD HH:MM:SS" or "M월 D일 HH:MM"
# Unacceptable: ISO with microseconds, PG timestamp text, UTC offset glyph (covered by L1).
# L3 catches: 12/24h ambiguity, missing leading zeros.
TIMESTAMP_BAD_NO_LEADING_ZERO = re.compile(
    r"\b\d{4}-\d{1}-\d{2}\b|\b\d{4}-\d{2}-\d{1}\b"
)  # 2026-5-19 or 2026-05-1
TIMESTAMP_BAD_12H_NO_MERIDIEM = re.compile(
    r"\b(?:1?[0-9]):[0-5][0-9]\s*(?![ap]m|시|분|오전|오후|AM|PM)"
)  # 8:30 without 오전/오후 — heuristic, conservative match

# --- currency format expectations ---
# Acceptable: "₩1,234,567" or "1,234,567원" or "1,234,567 KRW"
# Unacceptable: bare integer ≥ 4 digits without 원/₩/KRW (likely amount)
# Bare floats like "0.5%" pass-through. Heuristic: 4+ digit number with no
# unit suffix within 5 chars after, AND in body text (not numeric ID).
CURRENCY_BAD_BARE_AMOUNT = re.compile(
    r"(?<![\d.\w/-])\d{1,3}(?:,\d{3})+(?!,?\d)"
    r"(?![원\s]*(?:원|KRW|won)|\s*개|\s*명|\s*건)",
    re.IGNORECASE,
)
CURRENCY_BAD_NO_THOUSAND_SEP = re.compile(
    r"(?<![\d.\w])(?:₩|KRW\s+)\d{4,}(?!\d)|(?<![\d.\w])\d{4,}\s*원(?![\d])"
)  # ₩1234 instead of ₩1,234 ; 12345원 instead of 12,345원

# --- 호칭 consistency expectations ---
# Acceptable: "PB님", "WM님", "고객님", "{name}님" — 한국어 존댓말 (반말금지 룰)
# Unacceptable: "PB씨", "WM씨", or bare "고객" / "PB" / "WM" used as 호칭 위치
# Heuristic: detect 한국어 종결어미 직전에 호칭 노출
HONORIFIC_BAD_SSI = re.compile(r"\b(PB|WM|BRANCH_MANAGER|ADMIN)\s*씨")
HONORIFIC_BAD_RAW_ROLE = re.compile(
    r"(PB|WM|BRANCH_MANAGER|ADMIN)\s*(?:은|는|이|가)\s+"
)  # role used as subject directly without 님 suffix
# 영문 키 노출 (반말 검출 trigger 옆) — PRD §1.1 incident
HONORIFIC_BAD_ENGLISH_KEY = re.compile(
    r"\b(roleCode|userRole|displayName|profileName)\b"
)

L3_PATTERNS: dict[str, dict[str, re.Pattern[str]]] = {
    "timestamp": {
        "BAD_NO_LEADING_ZERO": TIMESTAMP_BAD_NO_LEADING_ZERO,
    },
    "currency": {
        "BAD_BARE_AMOUNT": CURRENCY_BAD_BARE_AMOUNT,
        "BAD_NO_THOUSAND_SEP": CURRENCY_BAD_NO_THOUSAND_SEP,
    },
    "honorific": {
        "BAD_SSI": HONORIFIC_BAD_SSI,
        "BAD_RAW_ROLE": HONORIFIC_BAD_RAW_ROLE,
        "BAD_ENGLISH_KEY": HONORIFIC_BAD_ENGLISH_KEY,
    },
}


@dataclass
class L3Finding:
    category: str
    pattern_name: str
    match_text: str
    offset: int


def scan_l3(text: str) -> list[L3Finding]:
    findings: list[L3Finding] = []
    for category, group in L3_PATTERNS.items():
        for name, pattern in group.items():
            for m in pattern.finditer(text):
                findings.append(L3Finding(
                    category=category,
                    pattern_name=name,
                    match_text=m.group(0),
                    offset=m.start(),
                ))
    return findings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L3 format consistency detector")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--text-file", type=pathlib.Path)
    src.add_argument("--text", type=str)
    src.add_argument("--stdin", action="store_true")
    args = p.parse_args(argv)

    if args.text_file is not None:
        text = args.text_file.read_text(encoding="utf-8")
    elif args.stdin:
        text = sys.stdin.read()
    else:
        text = args.text

    findings = scan_l3(text)
    result: dict[str, Any] = {
        "pass": len(findings) == 0,
        "findings_count": len(findings),
        "findings_by_category": {
            cat: sum(1 for f in findings if f.category == cat)
            for cat in L3_PATTERNS
        },
        "findings": [
            {"category": f.category, "pattern": f.pattern_name,
             "match": f.match_text, "offset": f.offset}
            for f in findings
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
