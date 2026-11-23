"""check_pending_measurements.py

Scan AI-06 and other ADR/Spec/SEC docs for [PENDING_MEASUREMENT:...] markers.
Parse owner/deadline/evidence_anchor fields.
Exit 1 if any deadline has expired (past current time).
Exit 0 otherwise.
Output: stderr listing all active PENDING_MEASUREMENT lines with days until deadline.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Docs to scan (relative to PROJECT_ROOT)
SCAN_PATHS = [
    "docs/ai/AI-06_nist_ai_rmf_mapping.md",
    "docs/architecture/ADR-007_validator_contract_specs.md",
    "docs/architecture/ADR-001_websocket_delivery_contract.md",
    "docs/architecture/ADR-002_email_authority_and_schema_contract.md",
    "docs/architecture/ADR-003_dependency_change_gate.md",
    "docs/architecture/ADR-004_poc_auto_approval_attestation.md",
    "docs/architecture/ADR-005_dual_llm_quarantine.md",
    "docs/architecture/ADR-006_audit_append_only_trigger.md",
    "docs/security/SEC-01_auth_spec.md",
    "docs/security/SEC-02_data_privacy.md",
]

# Regex: [PENDING_MEASUREMENT:owner=X,deadline=ISO8601,evidence_anchor=PATH]
MARKER_RE = re.compile(
    r"\[PENDING_MEASUREMENT:"
    r"owner=(?P<owner>[^,\]]+),"
    r"deadline=(?P<deadline>[^,\]]+),"
    r"evidence_anchor=(?P<evidence_anchor>[^\]]+)\]"
)


def parse_deadline(deadline_str: str) -> date:
    """Parse ISO 8601 date string (YYYY-MM-DD or full datetime)."""
    deadline_str = deadline_str.strip()
    try:
        return datetime.fromisoformat(deadline_str).date()
    except ValueError:
        return date.fromisoformat(deadline_str[:10])


def scan_file(path: Path) -> list[dict]:
    """Return list of dicts with file, line_no, owner, deadline, evidence_anchor."""
    findings = []
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in MARKER_RE.finditer(line):
            findings.append(
                {
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line_no": line_no,
                    "owner": m.group("owner"),
                    "deadline": m.group("deadline").strip(),
                    "evidence_anchor": m.group("evidence_anchor").strip(),
                    "raw_line": line.strip(),
                }
            )
    return findings


def main() -> int:
    today = datetime.now(tz=timezone.utc).date()
    all_findings: list[dict] = []

    for rel in SCAN_PATHS:
        all_findings.extend(scan_file(PROJECT_ROOT / rel))

    if not all_findings:
        print("check_pending_measurements: no PENDING_MEASUREMENT markers found.", file=sys.stderr)
        return 0

    expired: list[dict] = []
    active: list[dict] = []

    for f in all_findings:
        try:
            dl = parse_deadline(f["deadline"])
        except Exception as exc:
            print(
                f"WARN: cannot parse deadline '{f['deadline']}' in {f['file']}:{f['line_no']}: {exc}",
                file=sys.stderr,
            )
            expired.append(f)
            continue
        days_left = (dl - today).days
        f["days_left"] = days_left
        f["deadline_date"] = dl
        if days_left < 0:
            expired.append(f)
        else:
            active.append(f)

    # Print all active
    if active:
        print("PENDING_MEASUREMENT markers (active):", file=sys.stderr)
        for f in sorted(active, key=lambda x: x["deadline_date"]):
            print(
                f"  [{f['days_left']:+d}d] {f['file']}:{f['line_no']}"
                f"  owner={f['owner']}  deadline={f['deadline']}"
                f"  anchor={f['evidence_anchor']}",
                file=sys.stderr,
            )

    # Print expired
    if expired:
        print("EXPIRED PENDING_MEASUREMENT markers (deadline passed):", file=sys.stderr)
        for f in expired:
            days_left = f.get("days_left", "?")
            print(
                f"  [EXPIRED {days_left}d] {f['file']}:{f['line_no']}"
                f"  owner={f['owner']}  deadline={f['deadline']}"
                f"  anchor={f['evidence_anchor']}",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
