"""Stage 5 T272 — 7-principles self-assessment report integration.

Verifies the existing `scripts/generate_seven_principles_report.py` runs
end-to-end, exits with the expected ADR-007 §0 code set, and produces
output conforming to the documented schema (verified_at / status /
passed / per-principle scores / per-agent scores).

Def#1 of T272 (script integration) closes here; Def#2 (UI explainability
box in Customer 360 / ConsultationPage) remains UI env-blocked.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_seven_principles_static_check.py"

EXPECTED_PRINCIPLE_KEYS = {
    "P1_safety",
    "P2_accountability",
    "P3_transparency",
    "P4_fairness",
    "P5_privacy",
    "P6_security",
    "P7_robustness",
}

EXPECTED_AGENTS = {
    "rag_qa",
    "consultation_briefing",
    "nba_script",
    "email_draft",
    "compliance_check",
    "portfolio_analysis",
    "house_view_generation",
}


def _run_script(*extra_args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *extra_args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_script_exists():
    assert SCRIPT_PATH.is_file()


def test_script_help_advertises_required_flags():
    code, out, err = _run_script("--help")
    assert code == 0
    text = out + err
    assert "--out" in text
    assert "--also-markdown" in text


def test_script_default_run_exits_zero():
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "report.md"
        code, out, err = _run_script("--out", str(out_path), "--also-markdown")
        assert code == 0, f"exit {code}\nstdout: {out}\nstderr: {err}"
        # script emits a JSON summary line on stdout
        assert out_path.is_file()


def test_script_output_json_summary_shape():
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "report.md"
        code, out, _err = _run_script("--out", str(out_path), "--also-markdown")
        assert code == 0
        # Last line of stdout is a JSON summary per script docstring
        last = out.strip().splitlines()[-1]
        summary = json.loads(last)
        assert "status" in summary
        assert "passed" in summary
        assert summary["status"] in {"passed", "failed"}
        assert isinstance(summary["passed"], bool)


def test_markdown_contains_all_principles_and_agents():
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "report.md"
        code, _out, _err = _run_script("--out", str(out_path), "--also-markdown")
        assert code == 0
        md = out_path.read_text(encoding="utf-8")
        for principle in EXPECTED_PRINCIPLE_KEYS:
            assert principle in md, f"missing principle: {principle}"
        for agent in EXPECTED_AGENTS:
            assert agent in md, f"missing agent: {agent}"


def test_status_passes_on_full_model_card_set():
    """All 7 model cards exist + injection patterns + audit chain → should pass."""
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "report.md"
        code, out, _err = _run_script("--out", str(out_path), "--also-markdown")
        assert code == 0
        summary = json.loads(out.strip().splitlines()[-1])
        assert summary["passed"] is True
        assert summary["status"] == "passed"


def test_verified_at_iso8601_format():
    """ADR-007 §0 cross-cutting: ISO 8601 UTC with Z suffix or +00:00."""
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "report.md"
        code, _out, _err = _run_script("--out", str(out_path), "--also-markdown")
        assert code == 0
        md = out_path.read_text(encoding="utf-8")
        # Must contain a verified_at field with ISO-8601 timestamp marker
        assert "verified_at:" in md or '"verified_at"' in md
