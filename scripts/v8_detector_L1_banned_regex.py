#!/usr/bin/env python
"""v8_detector_L1_banned_regex.py — Stage 2 G2 deliverable (T103)

L1 BANNED regex detector. Deterministic (no LLM).
SoT: apps/web/e2e/_shared/banned-patterns.ts (v1.0, 10 patterns).

Each pattern ported from TypeScript regex to Python re with identical semantics.
Multi-line / case-insensitive flags preserved. Per-pattern test fixture in
tests/test_v8_detectors.py (50× determinism repeat).

Output: per-text PASS/FAIL with matched_pattern + offset.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any

# 10 BANNED patterns — ported from banned-patterns.ts v1.0
BANNED_ENGLISH = re.compile(
    r"\b(evidence|persisted|snapshot|universe|denominator|staff display)\b",
    re.IGNORECASE,
)
BANNED_INTERNAL_ID = re.compile(r"\b(ADR-\d+|W\d-T\d+|REG-0\d)\b")
BANNED_TEST_FIXTURE = re.compile(
    r"(GOLDEN_TEST|RALPH(?:-?QA)?|Synthetic boundary|golden regression test)"
)
BANNED_ISO_MICRO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+")
BANNED_PG_MICRO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+"
)
BANNED_PG_SHORT_TZ = re.compile(
    r"\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?[+-]\d{2}(?!:)"
)
BANNED_PLACEHOLDER = re.compile(
    r"응답을 기다리는 중|불러오는 중|로딩 중|최신 생성 정보 준비 중|"
    r"생성 대기|모델 대기"
)
BANNED_RAW_DB_FIELD = re.compile(
    r"\b(source_as_of|created_at|generated_at|observed_at)\b"
)
BANNED_AUDIT_PREFIX = re.compile(r"^AUDIT-(NEG|POS)-\d+", re.MULTILINE)
BANNED_DASH = re.compile(r"""(?:^|\s|["'])[-—](?:\s|["']|$)""")

PATTERNS: dict[str, re.Pattern[str]] = {
    "BANNED_ENGLISH": BANNED_ENGLISH,
    "BANNED_INTERNAL_ID": BANNED_INTERNAL_ID,
    "BANNED_TEST_FIXTURE": BANNED_TEST_FIXTURE,
    "BANNED_ISO_MICRO": BANNED_ISO_MICRO,
    "BANNED_PG_MICRO_TIMESTAMP": BANNED_PG_MICRO_TIMESTAMP,
    "BANNED_PG_SHORT_TZ": BANNED_PG_SHORT_TZ,
    "BANNED_PLACEHOLDER": BANNED_PLACEHOLDER,
    "BANNED_RAW_DB_FIELD": BANNED_RAW_DB_FIELD,
    "BANNED_AUDIT_PREFIX": BANNED_AUDIT_PREFIX,
    "BANNED_DASH": BANNED_DASH,
}


@dataclass
class L1Finding:
    pattern_name: str
    match_text: str
    offset: int


def scan_l1(text: str) -> list[L1Finding]:
    """Run all 10 BANNED patterns; return list of findings."""
    findings: list[L1Finding] = []
    for name, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            findings.append(L1Finding(
                pattern_name=name,
                match_text=m.group(0),
                offset=m.start(),
            ))
    return findings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L1 BANNED regex detector")
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

    findings = scan_l1(text)
    result: dict[str, Any] = {
        "pass": len(findings) == 0,
        "findings_count": len(findings),
        "findings": [
            {"pattern": f.pattern_name, "match": f.match_text, "offset": f.offset}
            for f in findings
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
