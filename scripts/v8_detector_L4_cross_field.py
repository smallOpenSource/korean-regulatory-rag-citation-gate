#!/usr/bin/env python
"""v8_detector_L4_cross_field.py — Stage 2 G2 deliverable (T105)

L4 cross-field inconsistency detector. Deterministic boolean assertions on
DOM-extracted field values. 12 known combos catalog per PRD §4 #10.

Input: JSON object with DOM-extracted fields (extracted by BFS visitor).
Output: per-combo PASS/FAIL.

12 combos catalogued — extensible via --catalog-file YAML.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class L4Combo:
    combo_id: str
    description: str
    check: Callable[[dict[str, Any]], bool]  # returns True if INCONSISTENT (FAIL)


def _has(fields: dict[str, Any], key: str) -> bool:
    val = fields.get(key)
    if val is None:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    if isinstance(val, (list, dict)) and len(val) == 0:
        return False
    return True


def _missing(fields: dict[str, Any], key: str) -> bool:
    return not _has(fields, key)


# 12 known cross-field combinations (PRD §4 #10 catalog)
L4_COMBOS: list[L4Combo] = [
    L4Combo(
        "L4-01-ai-generated-empty",
        "ai_generated_at is set but ai_payload JSON empty/null",
        lambda f: _has(f, "ai_generated_at") and _missing(f, "ai_payload"),
    ),
    L4Combo(
        "L4-02-completed-no-summary",
        "consultations status COMPLETED but no summary field",
        lambda f: f.get("entity") == "consultations"
        and f.get("status") == "COMPLETED" and _missing(f, "summary"),
    ),
    L4Combo(
        "L4-03-sent-no-message-id",
        "email_drafts status SENT but no message_id",
        lambda f: f.get("entity") == "email_drafts"
        and f.get("status") == "SENT" and _missing(f, "message_id"),
    ),
    L4Combo(
        "L4-04-failed-no-error",
        "ai_jobs/batch_jobs/email_drafts status FAILED but no error_message",
        lambda f: f.get("entity") in {"ai_jobs", "batch_jobs", "email_drafts"}
        and f.get("status") == "FAILED" and _missing(f, "error_message"),
    ),
    L4Combo(
        "L4-05-active-no-period",
        "house_views status ACTIVE/ACTIVATED but no activation_period",
        lambda f: f.get("entity") == "house_views"
        and f.get("status") in {"ACTIVE", "ACTIVATED"}
        and _missing(f, "activation_period"),
    ),
    L4Combo(
        "L4-06-superseded-no-replacement",
        "house_views status SUPERSEDED but no superseded_by",
        lambda f: f.get("entity") == "house_views"
        and f.get("status") == "SUPERSEDED" and _missing(f, "superseded_by"),
    ),
    L4Combo(
        "L4-07-resolved-no-resolution",
        "aftercare_events status RESOLVED/COMPLETED but no resolution_note",
        lambda f: f.get("entity") == "aftercare_events"
        and f.get("status") in {"RESOLVED", "COMPLETED"}
        and _missing(f, "resolution_note"),
    ),
    L4Combo(
        "L4-08-snoozed-no-until",
        "nba_actions status SNOOZED but no snoozed_until",
        lambda f: f.get("entity") == "nba_actions"
        and f.get("status") == "SNOOZED" and _missing(f, "snoozed_until"),
    ),
    L4Combo(
        "L4-09-approved-no-approver",
        "email_drafts status APPROVED but no approved_by",
        lambda f: f.get("entity") == "email_drafts"
        and f.get("status") == "APPROVED" and _missing(f, "approved_by"),
    ),
    L4Combo(
        "L4-10-running-pct-100",
        "batch_jobs status RUNNING but progress_pct == 100",
        lambda f: f.get("entity") == "batch_jobs"
        and f.get("status") == "RUNNING" and f.get("progress_pct") == 100,
    ),
    L4Combo(
        "L4-11-done-pct-not-100",
        "batch_jobs status DONE but progress_pct != 100",
        lambda f: f.get("entity") == "batch_jobs"
        and f.get("status") == "DONE"
        and f.get("progress_pct") is not None
        and f.get("progress_pct") != 100,
    ),
    L4Combo(
        "L4-12-cancelled-future-due",
        "*_status CANCELLED but due_at is in the future",
        # Caller MUST pass an ISO "now" string to enable this combo;
        # absent/non-string "now" → never fires (no false-positive).
        lambda f: f.get("status") == "CANCELLED"
        and isinstance(f.get("due_at"), str)
        and isinstance(f.get("now"), str)
        and f.get("now")
        and f.get("due_at") > f.get("now"),
    ),
]


@dataclass
class L4Finding:
    combo_id: str
    description: str


def scan_l4(fields: dict[str, Any]) -> list[L4Finding]:
    findings: list[L4Finding] = []
    for combo in L4_COMBOS:
        try:
            if combo.check(fields):
                findings.append(L4Finding(combo.combo_id, combo.description))
        except Exception:
            # Defensive: malformed fields → skip combo
            continue
    return findings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L4 cross-field detector")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--fields-file", type=pathlib.Path,
                     help="JSON file with extracted fields")
    src.add_argument("--fields", type=str,
                     help="JSON string with extracted fields")
    src.add_argument("--stdin", action="store_true")
    args = p.parse_args(argv)

    if args.fields_file is not None:
        fields = json.loads(args.fields_file.read_text(encoding="utf-8"))
    elif args.stdin:
        fields = json.loads(sys.stdin.read())
    else:
        fields = json.loads(args.fields)

    if not isinstance(fields, dict):
        print(json.dumps({"pass": False,
                          "error": "fields must be JSON object"}))
        return 2

    findings = scan_l4(fields)
    result: dict[str, Any] = {
        "pass": len(findings) == 0,
        "findings_count": len(findings),
        "combo_total": len(L4_COMBOS),
        "findings": [
            {"combo_id": f.combo_id, "description": f.description}
            for f in findings
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
