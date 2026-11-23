#!/usr/bin/env python3
"""validate_no_secrets.py — REG-05 T289 secret scan gate.

Wraps ``scripts/run_gitleaks_scan.sh`` and emits the ADR-007 validator JSON triple
(``{verified_at, status, passed}``) plus ``evidence_paths``.

Exit codes (ADR-007 contract):
  0 = pass (no findings)
  2 = fail (findings — sanitized JSON report attached)
  3 = config error (gitleaks unavailable, config missing, JSON parse failure)
  4 = token-budget exhaustion (N/A for gitleaks; reserved)

CLI:
  python scripts/validate_no_secrets.py            # working-tree scan
  python scripts/validate_no_secrets.py --git      # include git history
  python scripts/validate_no_secrets.py --json-only  # only print JSON (no human log)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_gitleaks_scan.sh"
REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"

EXIT_PASS = 0
EXIT_FAIL = 2
EXIT_CONFIG = 3
EXIT_TOKEN_BUDGET = 4


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def latest_gitleaks_report(since: float | None = None) -> Path | None:
    """Return the newest gitleaks-*.json report.

    When ``since`` (a ``time.time()`` epoch seconds value) is supplied, only
    reports whose mtime is >= ``since`` are considered. 이렇게 해야 직전
    subprocess가 리포트를 쓰기 전에 크래시했을 때 이전 실행의 오래된 리포트가
    이번 실행 결과로 잘못 귀속(stale attribution)되는 것을 막을 수 있습니다.
    """
    if not REPORT_DIR.exists():
        return None
    candidates = sorted(REPORT_DIR.glob("gitleaks-*.json"))
    if since is not None:
        candidates = [p for p in candidates if p.stat().st_mtime >= since]
    return candidates[-1] if candidates else None


def parse_findings(report_path: Path | None) -> tuple[int, list[dict]]:
    """Return (count, sanitized_summary). gitleaks --redact already redacts secret values."""
    if report_path is None or not report_path.exists():
        return 0, []
    try:
        data = json.loads(report_path.read_text() or "[]")
    except json.JSONDecodeError:
        return -1, []
    if not isinstance(data, list):
        return -1, []
    summary = []
    for item in data[:50]:  # cap to 50 in the JSON triple body
        summary.append(
            {
                "rule_id": item.get("RuleID") or item.get("Rule"),
                "file": item.get("File"),
                "line": item.get("StartLine") or item.get("Line"),
                "commit": item.get("Commit"),
                # gitleaks --redact replaces Match with REDACTED before writing the report
                "redacted_match": item.get("Match"),
            }
        )
    return len(data), summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git", action="store_true", help="Scan committed git history as well")
    parser.add_argument("--json-only", action="store_true", help="Print only the JSON triple")
    args = parser.parse_args()

    if not SCRIPT.exists():
        triple = {
            "verified_at": utcnow(),
            "status": "config_error",
            "passed": False,
            "reason": f"scanner script missing: {SCRIPT}",
            "evidence_paths": [],
        }
        sys.stdout.write(json.dumps(triple, indent=2) + "\n")
        return EXIT_CONFIG

    if not shutil.which("gitleaks"):
        triple = {
            "verified_at": utcnow(),
            "status": "config_error",
            "passed": False,
            "reason": "gitleaks binary not on PATH (ADR-003 pre-approved tool; install separately)",
            "evidence_paths": [],
        }
        sys.stdout.write(json.dumps(triple, indent=2) + "\n")
        return EXIT_CONFIG

    cmd = [str(SCRIPT)]
    if args.git:
        cmd.append("--git")

    if not args.json_only:
        sys.stderr.write(f"[validate_no_secrets] running: {' '.join(cmd)}\n")
    # subprocess 시작 직전 시각을 기록해 이번 실행이 새로 쓴 리포트만 채택합니다.
    scan_started_at = time.time()
    proc = subprocess.run(cmd, check=False)

    # 이번 실행이 정상 종료(0=pass, 2=findings)했고 그 이후 mtime의 리포트만 채택.
    # 그 외(크래시/config error)에는 stale 리포트 귀속을 막기 위해 증거를 붙이지 않습니다.
    report = None
    if proc.returncode in (EXIT_PASS, EXIT_FAIL):
        report = latest_gitleaks_report(since=scan_started_at)
    findings_count, findings_summary = parse_findings(report)
    evidence = [str(report.relative_to(PROJECT_ROOT))] if report else []

    if proc.returncode == 0:
        status = "pass"
        passed = True
        reason = "no secrets detected"
    elif proc.returncode == 2:
        status = "fail"
        passed = False
        if report is None:
            # findings를 보고했지만 이번 실행이 새로 쓴 리포트가 없는 경우(쓰기 전
            # 크래시 등). stale 리포트를 귀속시키지 않고 증거 없음을 명시합니다.
            reason = "findings detected but no fresh report from this run (no evidence attached)"
        elif findings_count < 0:
            # 리포트 파싱 실패(손상된 gitleaks JSON) 시 findings_count가 -1이 되어
            # "-1 finding(s)"로 보고되던 문제를 막기 위해 명시적으로 처리합니다.
            reason = "findings detected but report unparseable (corrupt gitleaks JSON)"
        else:
            reason = f"{findings_count} finding(s) — sanitized report attached"
    else:
        status = "config_error"
        passed = False
        reason = f"gitleaks wrapper exited {proc.returncode}"

    triple = {
        "verified_at": utcnow(),
        "status": status,
        "passed": passed,
        "reason": reason,
        "findings_count": findings_count if findings_count >= 0 else None,
        "findings_sample": findings_summary,
        "scan_mode": "git_history" if args.git else "working_tree",
        "evidence_paths": evidence,
    }
    sys.stdout.write(json.dumps(triple, indent=2) + "\n")

    if status == "pass":
        return EXIT_PASS
    if status == "fail":
        return EXIT_FAIL
    return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
