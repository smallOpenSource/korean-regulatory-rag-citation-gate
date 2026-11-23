#!/usr/bin/env python3
"""
endpoint_emit_grep.py — Grep action_code emit calls from routers/services

Scans Python source files for ``insert_audit_log(action_code=...)`` calls
(and equivalent variants) to produce a file:LINE map per action_code.
Intended for future-cycle Critic endpoint-emit verification
([[endpoint-emit-tracing-required]] M2 automation).

Usage:
    python scripts/endpoint_emit_grep.py [OPTIONS]

Options:
    --action_code NAME   Filter output to a single action_code (case-sensitive)
    --source PATHS       Comma-separated directories/files to scan
                         (default: apps/api/harness/api/routers,
                                   apps/api/harness/services)
    --text               Human-readable output: one "<code> @ <file>:<line>" per row
    --json               JSON output (default)

Exit codes:
    0  always — use grep on the output for CI assertions

Examples:
    # Full JSON map
    python scripts/endpoint_emit_grep.py

    # Filter single code
    python scripts/endpoint_emit_grep.py --action_code consultation_create

    # Human-readable
    python scripts/endpoint_emit_grep.py --text

    # Acceptance binary cross-check (12 T2-1 codes)
    python scripts/endpoint_emit_grep.py | python -m json.tool | \\
        grep -E "consultation_create|suitability_confirmed|..."

    # Forbidden codes check (expected: 0 hits)
    python scripts/endpoint_emit_grep.py | grep -E "outbound_email_sent|nba_progressed"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Default scan paths (anchored to project root so the gate works off any CWD)
# ---------------------------------------------------------------------------
# CWD-상대 경로면 repo 루트 밖에서 실행 시 빈 결과 + exit 0 (silent no-op)이
# 되므로, 기본 스캔 경로를 PROJECT_ROOT 기준 절대 경로로 고정합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES: list[str] = [
    str(PROJECT_ROOT / "apps/api/harness/api/routers"),
    str(PROJECT_ROOT / "apps/api/harness/services"),
]

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Pattern A — inline literal on the same line as the assignment/kwarg:
#   action_code="consultation_create"
#   action_code = "suitability_confirmed"
RE_INLINE = re.compile(r'action_code\s*=\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')

# Pattern B — multi-line parenthesised assignment (line ends with just "("):
#   action_code = (
#       "suitability_grade_block" if ...
#       else "suitability_confirmed"
#   )
RE_MULTILINE_START = re.compile(r'^\s*action_code\s*=\s*\(\s*$')

# Pattern C — string literals inside a multi-line ternary block.
# Two sub-patterns are checked per inner line (MULTILINE flag on compiled regex
# is not needed here; we match one line at a time):
#   1. String literal that starts the line (after optional whitespace):
#         "suitability_grade_block" if ...
#         "marketing_review_approved"
#   2. String literal immediately after the keyword `else`:
#         else "suitability_confirmed"
RE_INNER_LEADING = re.compile(r'^\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
RE_INNER_ELSE = re.compile(r'\belse\s+["\']([A-Za-z_][A-Za-z0-9_]*)["\']')

# Also catch alternate function names for future-proofing
# (no such calls exist in the codebase as of this script, but listed per spec)
_AUDIT_CALL_NAMES = re.compile(
    r'(?:insert_audit_log|audit_log|record_audit_event)\s*\('
)


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def scan_file(path: Path) -> list[dict[str, Any]]:
    """Return [{action_code, file, line}, ...] for a single Python file."""
    results: list[dict[str, Any]] = []
    rel = str(path)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return results

    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]

        # ------------------------------------------------------------------
        # Pattern A: inline literal
        # ------------------------------------------------------------------
        m = RE_INLINE.search(raw)
        if m:
            results.append({"action_code": m.group(1), "file": rel, "line": i + 1})
            i += 1
            continue

        # ------------------------------------------------------------------
        # Pattern B: multi-line ternary block starting with "action_code = ("
        # ------------------------------------------------------------------
        if RE_MULTILINE_START.search(raw):
            i += 1
            depth = 1  # we consumed the opening "("

            while i < n and depth > 0:
                inner = lines[i]

                # Update paren depth (handles nested calls inside conditions)
                depth += inner.count("(") - inner.count(")")

                # Collect string literals from this inner line
                lead = RE_INNER_LEADING.search(inner)
                if lead:
                    results.append({
                        "action_code": lead.group(1),
                        "file": rel,
                        "line": i + 1,
                    })

                else_m = RE_INNER_ELSE.search(inner)
                if else_m:
                    # Avoid double-adding if the leading match already caught it
                    if not lead or else_m.group(1) != lead.group(1):
                        results.append({
                            "action_code": else_m.group(1),
                            "file": rel,
                            "line": i + 1,
                        })

                i += 1
            continue

        i += 1

    return results


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, int]] = set()
    out: list[dict[str, Any]] = []
    for r in items:
        key = (r["action_code"], r["file"], r["line"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="endpoint_emit_grep.py",
        description="Grep action_code emit calls from API routers and services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--action_code",
        metavar="NAME",
        default=None,
        help="Filter output to a specific action_code (case-sensitive)",
    )
    p.add_argument(
        "--source",
        metavar="PATHS",
        default=",".join(DEFAULT_SOURCES),
        help=(
            "Comma-separated list of directories or .py files to scan "
            f"(default: {', '.join(DEFAULT_SOURCES)})"
        ),
    )
    output_group = p.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        dest="fmt",
        action="store_const",
        const="json",
        default="json",
        help="Output as JSON (default)",
    )
    output_group.add_argument(
        "--text",
        dest="fmt",
        action="store_const",
        const="text",
        help="Output as human-readable text: <action_code> @ <file>:<line>",
    )
    return p


def collect_py_files(source_spec: str) -> list[Path]:
    files: list[Path] = []
    for raw in source_spec.split(","):
        p = Path(raw.strip())
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file() and p.suffix == ".py":
            files.append(p)
        else:
            print(f"[warn] source path not found or not a .py file: {p}", file=sys.stderr)
    return files


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    py_files = collect_py_files(args.source)

    all_results: list[dict[str, Any]] = []
    for pf in py_files:
        all_results.extend(scan_file(pf))

    all_results = deduplicate(all_results)

    # Apply --action_code filter
    if args.action_code:
        all_results = [r for r in all_results if r["action_code"] == args.action_code]

    # Build output map: action_code → [{file, line}, ...]
    emit_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in all_results:
        emit_map[r["action_code"]].append({"file": r["file"], "line": r["line"]})

    sorted_map = dict(sorted(emit_map.items()))

    if args.fmt == "text":
        for code, locs in sorted_map.items():
            for loc in locs:
                print(f"{code} @ {loc['file']}:{loc['line']}")
    else:
        print(json.dumps(sorted_map, indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
