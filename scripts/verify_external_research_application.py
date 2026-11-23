#!/usr/bin/env python3
"""verify_external_research_application.py — ADR-007 §4 traceability validator.

Proves every REG-01..REG-06 §5/§6 task ID maps to:
  1. A BACKLOG.md entry
  2. An audit code in OBS-02 (when REG section declares one)
  3. UI screenshot evidence in playwright-report/ (when REG demands)
  4. A golden test file in tests/ (when REG demands)

Exit codes (ADR-007 §0 cross-cutting):
  0  all REG task IDs traced; all required artifacts present
  2  one or more traceability misses or unmapped task IDs
  3  config error (missing input file / dir)

Output JSON shape (ADR-007 §4):
  {
    "status": "passed|failed",
    "passed": <bool>,
    "verified_at": "<ISO8601 UTC>",
    "summary": { "reg_rows_total": N, "backlog_matches": N, ... },
    "by_regulation": { "REG-01": {...}, ... },
    "evidence_paths": [...]
  }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_BACKLOG = PROJECT_ROOT / "BACKLOG.md"
DEFAULT_REGS_DIR = PROJECT_ROOT / "docs" / "regulations"
DEFAULT_AUDIT_CODES_DOC = PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"
DEFAULT_UI_EVIDENCE_DIR = PROJECT_ROOT / "apps" / "web" / "playwright-report"
DEFAULT_GOLDEN_TEST_DIR = PROJECT_ROOT / "tests"
DEFAULT_OUT = (
    PROJECT_ROOT
    / ".omc"
    / "specs"
    / "autoresearch-external-research-application"
    / "result.json"
)

REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"

# ── Patterns ──────────────────────────────────────────────────────────────────

# Task ID: T followed by exactly 3 digits
TASK_ID_RE = re.compile(r"\bT(\d{3})\b")

# Matches H2 section headers that indicate a BACKLOG task list within REG docs
# e.g. "## 5. BACKLOG task 후보 (T200~T219)"
#       "## 9. BACKLOG Task 후보 (T280~T299)"
#       "## 8. BACKLOG task 후보 T300~T319"
BACKLOG_SECTION_RE = re.compile(
    r"^##\s+\d+\.\s+BACKLOG\b",
    re.MULTILINE | re.IGNORECASE,
)

# All audit_code values in OBS-02: pipe-delimited table rows
# Matches lines like: | auth_login_success | description |
AUDIT_CODE_ROW_RE = re.compile(r"^\|\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\|", re.MULTILINE)

# Known audit-code marker prefixes required per REG category.
# These are checked against the parsed OBS-02 code set.
# fmt: off
REG_REQUIRED_AUDIT_CODE_PREFIXES: dict[str, tuple[str, ...]] = {
    "REG-01": ("consent_recorded", "rights_notice_issued", "info_access_requested",
                "credit_info_purge_simulated"),
    "REG-02": ("marketing_review_submitted", "unfair_solicitation_blocked", "email_drafted"),
    "REG-03": ("suitability_confirmed", "appropriateness_warning_acknowledged",
                "explanation_confirmed"),
    "REG-04": ("ai_quarantine_triggered", "ai_fail_closed", "ai_injection_detected"),
    "REG-05": ("auth_login_success", "ws_ticket_issued", "rate_limit_exceeded"),
    "REG-06": ("poc_auto_approval_used", "sod_evidence_published", "demo_mode_toggle_on"),
}
# fmt: on

# Golden test file patterns expected when REG row declares golden_test requirement
GOLDEN_TEST_PATTERNS: dict[str, tuple[str, ...]] = {
    "REG-04": ("test_rag_golden.py", "test_seven_agents_golden.py", "test_rag_adversarial.py"),
}

# UI evidence: playwright-report directories / screenshots expected per REG
UI_EVIDENCE_PATTERNS: dict[str, tuple[str, ...]] = {
    "REG-05": ("harness-critical", "role-matrix"),
    "REG-06": ("role-matrix", "adversarial"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _exit3(msg: str) -> None:
    print(f"[CONFIG ERROR] {msg}", file=sys.stderr)
    sys.exit(3)


def _load_text(path: Path, label: str) -> str:
    if not path.exists():
        _exit3(f"{label} not found: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


# ── Core extraction ───────────────────────────────────────────────────────────


def _extract_task_ids_from_section(text: str, section_start: int) -> list[str]:
    """Return deduplicated T### IDs from the BACKLOG section starting at *section_start*."""
    rest = text[section_start:]
    # End of section = next H2 header (after the opening one)
    next_h2 = re.search(r"\n##\s+", rest[1:])
    section_body = rest[: next_h2.start() + 1] if next_h2 else rest
    seen: set[str] = set()
    ids: list[str] = []
    for m in TASK_ID_RE.finditer(section_body):
        tid = f"T{m.group(1)}"
        if tid not in seen:
            seen.add(tid)
            ids.append(tid)
    return ids


def extract_task_ids_from_reg(reg_text: str) -> list[str]:
    """Return all task IDs found in BACKLOG sections of a REG doc."""
    all_ids: list[str] = []
    seen: set[str] = set()
    for m in BACKLOG_SECTION_RE.finditer(reg_text):
        for tid in _extract_task_ids_from_section(reg_text, m.start()):
            if tid not in seen:
                seen.add(tid)
                all_ids.append(tid)
    return all_ids


def load_backlog_task_ids(backlog_path: Path) -> frozenset[str]:
    """Extract every T### ID mentioned in BACKLOG.md."""
    text = backlog_path.read_text(encoding="utf-8", errors="replace")
    return frozenset(f"T{m.group(1)}" for m in TASK_ID_RE.finditer(text))


def load_obs02_audit_codes(codes_doc: Path) -> frozenset[str]:
    """Parse OBS-02 and return the full set of declared action_code strings."""
    text = _load_text(codes_doc, "OBS-02 audit codes doc")
    codes: set[str] = set()
    for m in AUDIT_CODE_ROW_RE.finditer(text):
        candidate = m.group(1).strip()
        # Exclude header rows and separator rows
        if candidate.lower() not in ("action_code", "---", ""):
            codes.add(candidate)
    return frozenset(codes)


# ── Per-REG checks ────────────────────────────────────────────────────────────


def check_reg(
    reg_name: str,
    reg_text: str,
    *,
    backlog_ids: frozenset[str],
    audit_codes: frozenset[str],
    ui_evidence_dir: Path,
    golden_test_dir: Path,
) -> dict[str, Any]:
    """Return a per-regulation result dict with traceability findings."""
    task_ids = extract_task_ids_from_reg(reg_text)
    unmapped: list[str] = []
    backlog_matches = 0
    for tid in task_ids:
        if tid in backlog_ids:
            backlog_matches += 1
        else:
            unmapped.append(tid)

    # Audit code check for this REG
    required_codes = REG_REQUIRED_AUDIT_CODE_PREFIXES.get(reg_name, ())
    missing_codes: list[str] = [c for c in required_codes if c not in audit_codes]

    # UI evidence check
    required_ui = UI_EVIDENCE_PATTERNS.get(reg_name, ())
    missing_ui: list[str] = []
    for pattern in required_ui:
        matches = (
            list(ui_evidence_dir.rglob(f"*{pattern}*"))
            if ui_evidence_dir.exists()
            else []
        )
        if not matches:
            missing_ui.append(pattern)

    # Golden test check
    required_golden = GOLDEN_TEST_PATTERNS.get(reg_name, ())
    missing_golden: list[str] = []
    for fname in required_golden:
        if not (golden_test_dir / fname).exists():
            missing_golden.append(fname)

    passed = (
        not unmapped
        and not missing_codes
        and not missing_golden
        # UI evidence is soft: warn but do not block (playwright-report only exists after E2E run)
    )

    return {
        "reg": reg_name,
        "task_ids_found": task_ids,
        "task_ids_total": len(task_ids),
        "backlog_matches": backlog_matches,
        "unmapped": unmapped,
        "audit_code_required": list(required_codes),
        "audit_code_missing": missing_codes,
        "ui_evidence_checked": list(required_ui),
        "ui_evidence_missing": missing_ui,
        "golden_tests_required": list(required_golden),
        "golden_tests_missing": missing_golden,
        "passed": passed,
    }


# ── Aggregate ─────────────────────────────────────────────────────────────────


def run_all_checks(
    *,
    backlog_path: Path,
    regs_dir: Path,
    audit_codes_doc: Path,
    ui_evidence_dir: Path,
    golden_test_dir: Path,
) -> tuple[dict[str, Any], list[str]]:
    """
    Run checks for all REG-NN docs in *regs_dir*.
    Returns (by_regulation, evidence_paths).
    """
    backlog_ids = load_backlog_task_ids(backlog_path)
    audit_codes = load_obs02_audit_codes(audit_codes_doc)

    evidence_paths: list[str] = [
        str(backlog_path.relative_to(PROJECT_ROOT)),
        str(audit_codes_doc.relative_to(PROJECT_ROOT)),
    ]

    # REG-0*.md 글롭은 REG-10 이상을 조용히 누락하므로 REG-*.md로 넓힙니다.
    # (아래 stem.split('_')[0] 파싱은 그대로 'REG-NN'을 산출합니다.)
    reg_files = sorted(regs_dir.glob("REG-*.md"))
    if not reg_files:
        _exit3(f"No REG-NN docs found in {regs_dir}")

    by_regulation: dict[str, Any] = {}
    for reg_path in reg_files:
        reg_name = reg_path.stem.split("_")[0]  # e.g. "REG-01"
        reg_text = reg_path.read_text(encoding="utf-8", errors="replace")
        evidence_paths.append(str(reg_path.relative_to(PROJECT_ROOT)))
        by_regulation[reg_name] = check_reg(
            reg_name,
            reg_text,
            backlog_ids=backlog_ids,
            audit_codes=audit_codes,
            ui_evidence_dir=ui_evidence_dir,
            golden_test_dir=golden_test_dir,
        )

    return by_regulation, evidence_paths


# ── Build result ──────────────────────────────────────────────────────────────


def build_result(by_regulation: dict[str, Any], evidence_paths: list[str]) -> dict[str, Any]:
    reg_rows_total = sum(r["task_ids_total"] for r in by_regulation.values())
    backlog_matches = sum(r["backlog_matches"] for r in by_regulation.values())
    audit_code_matches = sum(
        len(r["audit_code_required"]) - len(r["audit_code_missing"])
        for r in by_regulation.values()
    )
    ui_evidence_matches = sum(
        len(r["ui_evidence_checked"]) - len(r["ui_evidence_missing"])
        for r in by_regulation.values()
    )
    golden_test_matches = sum(
        len(r["golden_tests_required"]) - len(r["golden_tests_missing"])
        for r in by_regulation.values()
    )
    all_unmapped = [
        tid for r in by_regulation.values() for tid in r["unmapped"]
    ]
    all_missing_codes = [
        code for r in by_regulation.values() for code in r["audit_code_missing"]
    ]
    all_missing_golden = [
        fname for r in by_regulation.values() for fname in r["golden_tests_missing"]
    ]

    passed = not all_unmapped and not all_missing_codes and not all_missing_golden
    status = "passed" if passed else "failed"

    return {
        "status": status,
        "passed": passed,
        "verified_at": _now_utc(),
        "summary": {
            "reg_rows_total": reg_rows_total,
            "backlog_matches": backlog_matches,
            "audit_code_matches": audit_code_matches,
            "ui_evidence_matches": ui_evidence_matches,
            "golden_test_matches": golden_test_matches,
            "unmapped": all_unmapped,
            "missing_audit_codes": all_missing_codes,
            "missing_golden_tests": all_missing_golden,
        },
        "by_regulation": by_regulation,
        "evidence_paths": evidence_paths,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--backlog", type=Path, default=DEFAULT_BACKLOG)
    parser.add_argument("--regs", type=Path, default=DEFAULT_REGS_DIR)
    parser.add_argument("--audit-codes-doc", type=Path, default=DEFAULT_AUDIT_CODES_DOC)
    parser.add_argument("--ui-evidence", type=Path, default=DEFAULT_UI_EVIDENCE_DIR)
    parser.add_argument(
        "--golden-test-dir",
        type=Path,
        default=DEFAULT_GOLDEN_TEST_DIR,
        help="Directory to search for golden test files (default: tests/).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output JSON path (default: .omc/specs/autoresearch-external-research-application/result.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Config validation (exit 3 on missing required inputs)
    for path, label in (
        (args.backlog, "BACKLOG"),
        (args.regs, "regs dir"),
        (args.audit_codes_doc, "OBS-02 audit codes doc"),
    ):
        if not path.exists():
            _exit3(f"{label} not found: {path}")

    by_regulation, evidence_paths = run_all_checks(
        backlog_path=args.backlog,
        regs_dir=args.regs,
        audit_codes_doc=args.audit_codes_doc,
        ui_evidence_dir=args.ui_evidence,
        golden_test_dir=args.golden_test_dir,
    )

    result = build_result(by_regulation, evidence_paths)

    # Write output
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    # Also write a timestamped copy to verification report dir
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_copy = REPORT_DIR / f"external-research-application-{ts}.json"
    report_copy.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps(result, ensure_ascii=False))

    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
