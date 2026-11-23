#!/usr/bin/env python3
"""Cleanup stale runtime measurement JSONs (Deliverable 6).

Scans docs/ai/measurements/*.json and archives files that are either:
  - Older than 30 days by mtime
  - Have an ``expires_at`` field that is in the past

Archived files are moved to docs/ai/measurements/archive/ (not deleted).
Operation is idempotent: running twice with the same state produces the same result.

Exit codes:
    0 — completed (no errors; even if no files archived or dir missing)
    2 — one or more files failed to archive (OSError)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENTS_DIR = PROJECT_ROOT / "docs" / "ai" / "measurements"
ARCHIVE_DIR = MEASUREMENTS_DIR / "archive"
STALE_MTIME_DAYS = 30


def is_stale(fpath: Path, now: datetime) -> bool:
    """Return True if the file should be archived."""
    # Check expires_at field first (authoritative)
    try:
        payload = json.loads(fpath.read_text(encoding="utf-8"))
        expires_str = payload.get("expires_at", "")
        if expires_str:
            expires_at = datetime.strptime(expires_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if now > expires_at:
                return True
    except (json.JSONDecodeError, ValueError, OSError):
        pass  # fall through to mtime check

    # Fall back to mtime check
    try:
        mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=UTC)
        if (now - mtime) > timedelta(days=STALE_MTIME_DAYS):
            return True
    except OSError:
        pass

    return False


def run(measurements_dir: Path, archive_dir: Path, *, dry_run: bool = False) -> int:
    """Scan and archive stale measurement files. Returns exit code."""
    if not measurements_dir.exists():
        print(json.dumps({
            "status": "passed",
            "passed": True,
            "archived": [],
            "note": f"measurements dir does not exist: {measurements_dir}",
        }))
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    archived: list[str] = []
    errors: list[str] = []

    for fpath in sorted(measurements_dir.glob("*.json")):
        if fpath.name.startswith("."):
            continue
        if not is_stale(fpath, now):
            continue

        dest = archive_dir / fpath.name
        # Handle name collision idempotently
        if dest.exists():
            # Already archived — skip
            continue

        if dry_run:
            archived.append(str(fpath.relative_to(PROJECT_ROOT)))
        else:
            try:
                shutil.move(str(fpath), str(dest))
                archived.append(str(fpath.relative_to(PROJECT_ROOT)))
            except OSError as exc:
                errors.append(f"failed to archive {fpath.name}: {exc}")

    result = {
        "status": "failed" if errors else "passed",
        "passed": not errors,
        "dry_run": dry_run,
        "archived_count": len(archived),
        "archived": archived,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 2 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measurements-dir",
        type=Path,
        default=MEASUREMENTS_DIR,
        help="Directory containing measurement JSON files.",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=ARCHIVE_DIR,
        help="Destination archive directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report stale files without moving them.",
    )
    args = parser.parse_args(argv)
    return run(args.measurements_dir, args.archive_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
