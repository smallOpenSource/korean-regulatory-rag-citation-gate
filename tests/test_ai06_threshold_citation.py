"""test_ai06_threshold_citation.py  (AC9)

Parse AI-06.md and assert that every quantitative threshold line (containing ≥ or ≤)
carries either:
  - a citation  (source: <path>  ...last_measured_at: ...)
  - a [PENDING_MEASUREMENT:owner=X,deadline=ISO8601,evidence_anchor=PATH] label

Also validates the PENDING_MEASUREMENT schema: all three fields must be present and
the deadline must be a parseable ISO-8601 date.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI06_PATH = PROJECT_ROOT / "docs" / "ai" / "AI-06_nist_ai_rmf_mapping.md"

# Lines containing a quantitative threshold operator
THRESHOLD_RE = re.compile(r"[≥≤]")

# Citation pattern: source: <path>
CITATION_RE = re.compile(r"source:\s*\S+")

# Full PENDING_MEASUREMENT schema: [PENDING_MEASUREMENT:owner=X,deadline=ISO8601,evidence_anchor=PATH]
PENDING_FULL_RE = re.compile(
    r"\[PENDING_MEASUREMENT:"
    r"owner=(?P<owner>[^,\]]+),"
    r"deadline=(?P<deadline>[^,\]]+),"
    r"evidence_anchor=(?P<evidence_anchor>[^\]]+)\]"
)

# Bare (malformed) PENDING_MEASUREMENT — present but missing required fields
PENDING_BARE_RE = re.compile(r"\[PENDING_MEASUREMENT[^\]]*\]")


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|---") or set(stripped) <= set("|-: ")


def _threshold_lines() -> list[tuple[int, str]]:
    """Return (line_no, line) for every threshold specification line in AI-06.

    Excludes:
    - Table separator rows
    - Lines inside the §5 GAI Risk Categories matrix (narrative cells, not threshold specs)

    Only §3 MEASURE function rows and §6 Threshold Reference table rows are in scope.
    """
    assert AI06_PATH.exists(), f"AI-06 not found at {AI06_PATH}"
    lines = AI06_PATH.read_text(encoding="utf-8").splitlines()

    # Determine line ranges to exclude (§5 GAI matrix: between "## 5." and next "## ")
    excluded_ranges: list[tuple[int, int]] = []
    in_gai_section = False
    section5_start = 0
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## 5.") or stripped == "## 5. 12 GAI Risk Categories × 7 Agents Matrix":
            in_gai_section = True
            section5_start = i
        elif in_gai_section and stripped.startswith("## ") and not stripped.startswith("## 5."):
            excluded_ranges.append((section5_start, i - 1))
            in_gai_section = False
    if in_gai_section:
        excluded_ranges.append((section5_start, len(lines)))

    def _is_excluded(line_no: int) -> bool:
        return any(start <= line_no <= end for start, end in excluded_ranges)

    result = []
    for line_no, line in enumerate(lines, start=1):
        if _is_excluded(line_no):
            continue
        if THRESHOLD_RE.search(line) and not _is_table_separator(line):
            result.append((line_no, line))
    return result


def test_ai06_exists() -> None:
    assert AI06_PATH.exists(), f"AI-06_nist_ai_rmf_mapping.md not found at {AI06_PATH}"


def test_threshold_lines_have_citation_or_pending() -> None:
    """Every ≥/≤ threshold line must have a citation or PENDING_MEASUREMENT label."""
    threshold_lines = _threshold_lines()
    assert threshold_lines, "No threshold lines found in AI-06 — document may be empty or regex wrong"

    violations: list[str] = []
    for line_no, line in threshold_lines:
        has_citation = bool(CITATION_RE.search(line))
        has_pending = bool(PENDING_BARE_RE.search(line))
        if not has_citation and not has_pending:
            violations.append(
                f"  AI-06:{line_no}: missing citation or PENDING_MEASUREMENT label\n"
                f"    line: {line.strip()[:120]}"
            )

    assert not violations, (
        f"{len(violations)} threshold line(s) missing citation or PENDING_MEASUREMENT:\n"
        + "\n".join(violations)
    )


def test_pending_measurement_schema_valid() -> None:
    """All [PENDING_MEASUREMENT:...] markers must have owner, deadline, and evidence_anchor."""
    assert AI06_PATH.exists()
    text = AI06_PATH.read_text(encoding="utf-8")

    # Find all bare markers first (any [...PENDING_MEASUREMENT...])
    bare_matches = list(PENDING_BARE_RE.finditer(text))
    if not bare_matches:
        pytest.skip("No PENDING_MEASUREMENT markers found — nothing to validate")

    schema_violations: list[str] = []
    deadline_violations: list[str] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in PENDING_BARE_RE.finditer(line):
            marker_text = m.group(0)
            full_m = PENDING_FULL_RE.search(marker_text)
            if not full_m:
                schema_violations.append(
                    f"  AI-06:{line_no}: malformed PENDING_MEASUREMENT (missing owner/deadline/evidence_anchor)\n"
                    f"    marker: {marker_text}"
                )
                continue

            # Validate deadline is parseable ISO-8601
            deadline_str = full_m.group("deadline").strip()
            try:
                date.fromisoformat(deadline_str[:10])
            except ValueError:
                deadline_violations.append(
                    f"  AI-06:{line_no}: deadline '{deadline_str}' is not a valid ISO-8601 date"
                )

    all_violations = schema_violations + deadline_violations
    assert not all_violations, (
        f"{len(all_violations)} PENDING_MEASUREMENT schema violation(s):\n"
        + "\n".join(all_violations)
    )


def test_pending_measurement_evidence_anchor_not_empty() -> None:
    """evidence_anchor field must be a non-empty string."""
    assert AI06_PATH.exists()
    text = AI06_PATH.read_text(encoding="utf-8")

    violations: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in PENDING_FULL_RE.finditer(line):
            anchor = m.group("evidence_anchor").strip()
            if not anchor:
                violations.append(f"  AI-06:{line_no}: evidence_anchor is empty")

    assert not violations, "\n".join(violations)


def test_pending_measurement_owner_not_empty() -> None:
    """owner field must be a non-empty string."""
    assert AI06_PATH.exists()
    text = AI06_PATH.read_text(encoding="utf-8")

    violations: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in PENDING_FULL_RE.finditer(line):
            owner = m.group("owner").strip()
            if not owner:
                violations.append(f"  AI-06:{line_no}: owner is empty")

    assert not violations, "\n".join(violations)
