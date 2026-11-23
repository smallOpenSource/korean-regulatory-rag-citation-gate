#!/usr/bin/env python3
"""Cron-able wrapper that invokes aggregate_principle_runtime_metrics.py for all 7 principles.

Calls aggregate_principle_runtime_metrics.py for the specified window,
which internally iterates all 7 principles × their metrics. This script
serves as the cron entry-point for scheduled measurement collection.

Usage:
    python collect_seven_principles_measurements.py --window=YYYY-MM-DD
    python collect_seven_principles_measurements.py --window=YYYY-MM-DD --dry-run

Exit codes:
    0 — all measurements collected
    2 — one or more measurements failed
    3 — config error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGGREGATOR = PROJECT_ROOT / "scripts" / "aggregate_principle_runtime_metrics.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window",
        required=True,
        metavar="YYYY-MM-DD",
        help="UTC calendar-day window for metrics aggregation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to aggregator (validates connectivity, emits no files)",
    )
    args = parser.parse_args(argv)

    cmd = [sys.executable, str(AGGREGATOR), f"--window={args.window}"]
    if args.dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        msg = "aggregate_principle_runtime_metrics.py timed out after 120s"
        print(json.dumps({"status": "failed", "passed": False, "error": msg}), file=sys.stderr)
        return 2

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
