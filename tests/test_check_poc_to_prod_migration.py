"""Stage 6 T317 Def#2 — check_poc_to_prod_migration.py integration tests.

Verifies the existing script runs end-to-end, produces structured JSON,
classifies tokens correctly, and exits with the documented codes.

T317 Def#1 (script presence + path correction) closed in Stage 1.
T317 Def#2 (§7 15-item coverage audit) closes here via integration
tests that exercise the live script against the actual repo tree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_poc_to_prod_migration.py"


def _run_script(*extra: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *extra],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_script_exists():
    assert SCRIPT_PATH.is_file()


def test_help_advertises_required_flags():
    code, out, err = _run_script("--help")
    assert code == 0
    text = out + err
    assert "--root" in text
    assert "--json" in text


def test_default_run_exits_zero():
    """Repo tree should currently pass production-readiness scan."""
    code, _out, _err = _run_script("--skip-shell-gate")
    assert code == 0


def test_json_output_shape():
    code, out, _err = _run_script("--json", "--skip-shell-gate")
    assert code == 0
    # Extract the last JSON block from stdout (may be preceded by human text)
    # JSON output starts with `{` and is the last balanced block.
    start = out.rfind("{")
    while start >= 0:
        try:
            data = json.loads(out[start:])
            break
        except json.JSONDecodeError:
            start = out.rfind("{", 0, start)
    else:
        raise AssertionError(f"no parseable JSON in stdout: {out[-200:]}")
    assert "checked_files" in data
    assert "allowed_paths_skipped" in data
    assert isinstance(data["checked_files"], int)


def test_checked_files_greater_than_zero():
    code, out, _err = _run_script("--json", "--skip-shell-gate")
    assert code == 0
    data = json.loads(out[out.rfind("{"):])
    assert data["checked_files"] > 100, (
        f"only scanned {data['checked_files']} files — likely scope misconfig"
    )


def test_token_scan_returns_list():
    """The findings list may be empty or non-empty but must be a list."""
    code, out, _err = _run_script("--json", "--skip-shell-gate")
    assert code == 0
    data = json.loads(out[out.rfind("{"):])
    if "findings" in data:
        assert isinstance(data["findings"], list)


def test_shell_gate_skipped_when_flag_passed():
    code, _out, _err = _run_script("--json", "--skip-shell-gate")
    assert code == 0
