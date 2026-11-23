"""Smoke tests for scripts/preflight_adr_amendments.sh.

Covers:
- Default state (all skip) → exit 0
- Pinned hash mismatch case → exit 1
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "preflight_adr_amendments.sh"
DEFAULT_PINNED = REPO_ROOT / "scripts" / "cycle2-adr-pinned.txt"


def _run_script(pinned_file: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **__import__("os").environ,
            "PINNED_FILE": str(pinned_file),
        },
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_script_exists():
    assert SCRIPT_PATH.is_file(), f"Script not found: {SCRIPT_PATH}"


def test_default_pinned_file_exists():
    assert DEFAULT_PINNED.is_file(), f"Pinned state file not found: {DEFAULT_PINNED}"


def test_all_skip_exits_zero():
    """Default state: all entries are 'skip' → exit 0."""
    content = (
        "# Pinned ADR commit hashes for Cycle 2 amendment integrity check.\n"
        "# Update after each amendment commit. 'skip' = no amendment needed for default path.\n"
        "ADR-003=skip\n"
        "ADR-005-section-1=skip\n"
        "ADR-005-section-3=skip\n"
        "ADR-005-section-5=skip\n"
        "ADR-007-section-2=skip\n"
        "ADR-007-section-4=skip\n"
        "V041=skip\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        tmp_path = Path(f.name)
    try:
        code, out, err = _run_script(tmp_path)
        assert code == 0, f"Expected exit 0 for all-skip; got {code}\nstdout={out}\nstderr={err}"
        assert "PREFLIGHT PASSED" in out, f"Expected PREFLIGHT PASSED in output; got:\n{out}"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_default_pinned_file_all_skip_exits_zero():
    """The shipped cycle2-adr-pinned.txt (initial state) must exit 0."""
    code, out, err = _run_script(DEFAULT_PINNED)
    assert code == 0, (
        f"Default pinned file should exit 0 (all skip); got {code}\n"
        f"stdout={out}\nstderr={err}"
    )
    assert "PREFLIGHT PASSED" in out


def test_invalid_hash_exits_one():
    """A non-skip entry with a bogus commit hash → exit 1."""
    content = (
        "ADR-003=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
        "ADR-005-section-1=skip\n"
        "ADR-005-section-3=skip\n"
        "ADR-005-section-5=skip\n"
        "ADR-007-section-2=skip\n"
        "ADR-007-section-4=skip\n"
        "V041=skip\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        tmp_path = Path(f.name)
    try:
        code, out, err = _run_script(tmp_path)
        assert code == 1, (
            f"Expected exit 1 for bogus hash; got {code}\nstdout={out}\nstderr={err}"
        )
        combined = out + err
        assert "FAIL" in combined or "not found" in combined, (
            f"Expected failure message; got:\n{combined}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_empty_value_exits_one():
    """An entry with an empty value (not 'skip') → exit 1."""
    content = (
        "ADR-003=\n"
        "ADR-005-section-1=skip\n"
        "ADR-005-section-3=skip\n"
        "ADR-005-section-5=skip\n"
        "ADR-007-section-2=skip\n"
        "ADR-007-section-4=skip\n"
        "V041=skip\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        tmp_path = Path(f.name)
    try:
        code, out, err = _run_script(tmp_path)
        assert code == 1, (
            f"Expected exit 1 for empty pin value; got {code}\nstdout={out}\nstderr={err}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)
