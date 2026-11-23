"""audit_ai06_measurement_freshness.py

Parse AI-06.md quantitative threshold lines.
For each line containing ≥ or ≤:
  - Assert either a citation (source: path/to/measurement) or [PENDING_MEASUREMENT:...] label exists.
  - If citation exists, check freshness from the inline measurement timestamp the doc
    actually uses: `verified_at=YYYY-MM-DD` (or full ISO) or `last_measured_at:`. The
    mtime fallback applies ONLY to .json measurement files — a .py source's mtime is
    code-touch recency, not measurement freshness, so a non-.json source without an
    inline timestamp is treated as non-authoritative (reported, not silently fresh).
  - If stale or missing label: exit 1 + WARN.

Exit 0 if all threshold lines are labelled and fresh.
Exit 1 if any threshold line is missing a label, or has a stale citation.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI06_PATH = PROJECT_ROOT / "docs" / "ai" / "AI-06_nist_ai_rmf_mapping.md"

FRESHNESS_WINDOW_DAYS = 7

# Matches lines that contain a quantitative threshold operator
THRESHOLD_RE = re.compile(r"[≥≤]")

# Matches citation: source: <path> plus an optional inline measurement timestamp.
# AI-06 embeds the measurement date inline as `verified_at=YYYY-MM-DD` (or full ISO);
# older callers used `last_measured_at:`. Accept both keys with either ':' or '=' as the
# separator so the ts group is actually populated (previously only `last_measured_at:`
# matched, so ts was always None and freshness silently fell back to file mtime).
CITATION_RE = re.compile(
    r"source:\s*(?P<path>\S+)"
    r"(?:.*(?:last_measured_at|verified_at)\s*[:=]\s*(?P<ts>[0-9T:Z\-]+))?"
)

# Matches PENDING_MEASUREMENT label
PENDING_RE = re.compile(
    r"\[PENDING_MEASUREMENT:"
    r"owner=(?P<owner>[^,\]]+),"
    r"deadline=(?P<deadline>[^,\]]+),"
    r"evidence_anchor=(?P<evidence_anchor>[^\]]+)\]"
)


def is_fresh(path_str: str, ts_str: str | None) -> tuple[bool, str]:
    """Return (is_fresh, reason). Check last_measured_at field first, then mtime."""
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=FRESHNESS_WINDOW_DAYS)

    # Check last_measured_at field in JSON
    if ts_str:
        try:
            measured_at = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
            if measured_at >= cutoff:
                return True, f"measured_at={ts_str} is within {FRESHNESS_WINDOW_DAYS}d"
            else:
                return False, f"measured_at={ts_str} is stale (>{FRESHNESS_WINDOW_DAYS}d old)"
        except ValueError:
            pass

    # Resolve the cited source. Source-code (.py) mtime is NOT a measurement-freshness
    # signal, so only .json measurement files may fall back to mtime; a non-.json source
    # without an inline timestamp is reported as non-authoritative rather than "fresh".
    json_path = PROJECT_ROOT / path_str.lstrip("/")
    if not json_path.exists():
        return False, f"source file not found: {path_str}"
    if json_path.suffix != ".json":
        return False, (
            f"non-authoritative source (not .json): {path_str} — no inline "
            f"verified_at=/last_measured_at: timestamp to verify freshness"
        )

    # .json measurement file: prefer its last_measured_at field, else fall back to mtime.
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if "last_measured_at" in data:
            ts = data["last_measured_at"]
            measured_at = datetime.fromisoformat(ts.rstrip("Z")).replace(tzinfo=timezone.utc)
            if measured_at >= cutoff:
                return True, f"JSON last_measured_at={ts} is within {FRESHNESS_WINDOW_DAYS}d"
            else:
                return False, f"JSON last_measured_at={ts} is stale (>{FRESHNESS_WINDOW_DAYS}d old)"
    except Exception:
        pass

    mtime = datetime.fromtimestamp(json_path.stat().st_mtime, tz=timezone.utc)
    if mtime >= cutoff:
        return True, f"mtime={mtime.isoformat()} is within {FRESHNESS_WINDOW_DAYS}d"
    return False, f"mtime={mtime.isoformat()} is stale (>{FRESHNESS_WINDOW_DAYS}d old)"


def _gai_section_excluded_lines(lines: list[str]) -> set[int]:
    """Return 1-based line numbers belonging to the §5 GAI Risk matrix (narrative cells)."""
    excluded: set[int] = set()
    in_gai = False
    section5_start = 0
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## 5."):
            in_gai = True
            section5_start = i
        elif in_gai and stripped.startswith("## ") and not stripped.startswith("## 5."):
            for n in range(section5_start, i):
                excluded.add(n)
            in_gai = False
    if in_gai:
        for n in range(section5_start, len(lines) + 1):
            excluded.add(n)
    return excluded


def main() -> int:
    if not AI06_PATH.exists():
        print(f"WARN: AI-06 not found at {AI06_PATH}", file=sys.stderr)
        return 1

    lines = AI06_PATH.read_text(encoding="utf-8").splitlines()
    excluded = _gai_section_excluded_lines(lines)
    errors: list[str] = []
    warnings: list[str] = []

    for line_no, line in enumerate(lines, start=1):
        if line_no in excluded:
            continue
        if not THRESHOLD_RE.search(line):
            continue
        # Skip table header/separator lines
        stripped = line.strip()
        if stripped.startswith("|---") or stripped == "|---|---|---|---|---|":
            continue

        has_pending = bool(PENDING_RE.search(line))
        citation_match = CITATION_RE.search(line)

        if has_pending:
            # Valid: labelled with PENDING_MEASUREMENT
            warnings.append(
                f"  PENDING  {AI06_PATH.name}:{line_no}: {stripped[:120]}"
            )
            continue

        if citation_match:
            path_str = citation_match.group("path")
            ts_str = citation_match.group("ts")
            fresh, reason = is_fresh(path_str, ts_str)
            if fresh:
                pass  # OK
            else:
                errors.append(
                    f"  STALE    {AI06_PATH.name}:{line_no}: citation source={path_str} — {reason}"
                )
            continue

        # No label and no citation — missing
        errors.append(
            f"  MISSING  {AI06_PATH.name}:{line_no}: threshold line has no citation or PENDING_MEASUREMENT label\n"
            f"           line: {stripped[:120]}"
        )

    if warnings:
        print("audit_ai06_measurement_freshness: PENDING_MEASUREMENT markers:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)

    if errors:
        print("audit_ai06_measurement_freshness: ERRORS:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    total = len(warnings)
    print(
        f"audit_ai06_measurement_freshness: OK — {total} PENDING_MEASUREMENT marker(s), 0 missing, 0 stale.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
