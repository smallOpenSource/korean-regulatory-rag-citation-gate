"""Final verification gate integration tests — W5-T2.

Validates:
  1. Both W5 validators emit ADR-007-compliant JSON triples
     (verified_at, status, passed, evidence_paths).
  2. Exit codes: 0=pass, 2=fail, 3=config-error for both scripts.
  3. verify_total_product_readiness.py aggregation components:
     - ext_dep_attestation (passed / failed)
     - sod_evidence (passed / failed / violations)
     - reg_audit_codes passes against real OBS-02 doc
     - dev_docs_exist passes (DEV-05..DEV-08 present)
     - module_split_diff_zero passes (all split submodules ≤ 500 lines)
  4. verify_external_research_application.py traceability:
     - Full 120-task pass against real REG docs + BACKLOG.
     - Unmapped task IDs → exit 2.
     - Missing BACKLOG → exit 3.
     - Missing regs dir → exit 3.
  5. ADR-007 JSON triple present in both scripts' output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_external_research_application as vera
from scripts import verify_total_product_readiness as vtpr

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Shared synthetic helpers (mirrored from test_total_product_readiness_validator) ──


def _gate_report(*, omit_step: str | None = None, failed_step: str | None = None) -> str:
    lines = [
        "# Verification Gate Evidence",
        "- started_at_utc: 2026-05-16T00:00:00Z",
        "- harness_root: .",
        "- python: /opt/conda/envs/wm_env/bin/python",
    ]
    for name in (*vtpr.REQUIRED_GATE_STEPS, *vtpr.DIAGNOSTIC_GATE_STEPS):
        if name == omit_step:
            continue
        status = 7 if name == failed_step else 0
        diagnostic = "; non-blocking diagnostic" if name in vtpr.DIAGNOSTIC_GATE_STEPS else ""
        lines.extend([
            f"## {name}", "```console", f"$ echo {name}",
            "ok" if not status else "ERROR",
            f"(exit {status}{diagnostic})", "```",
        ])
    lines.extend(["## Summary", "- finished_at_utc: 2026-05-16T00:01:00Z", "- failures: 0"])
    return "\n".join(lines) + "\n"


def _serviceable_result(*, passed: bool = True) -> dict:
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "verifier_signoff": "serviceable-readiness-validator" if passed else None,
        "selected_count": 200,
        "coverage_ratio": 1.0,
        "readiness": {"coverage": {
            "selected_count": 200,
            "coverage_ratio": 1.0,
            "missing_member_days": 0,
        }},
    }


def _attestation_json(*, passed: bool = True) -> dict:
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "verified_at": "2026-05-16T00:00:00Z",
        "window": {"start": "2026-05-15T00:00:00Z", "end": "2026-05-16T00:00:00Z"},
        "env_profile": "poc",
        "deps": {
            "azure_gpt5_mini": {
                "status": "passed" if passed else "failed",
                "agent_calls": [],
                "degraded_reason": None,
            },
            "smtp_sandbox": {"status": "passed", "transport": "mailpit",
                             "message_id": "test@test", "recipient": "r@example.invalid",
                             "degraded_reason": None},
            "broker_live_quote": {"status": "degraded", "symbol": "005930", "price": None,
                               "as_of": "2026-05-16T00:00:00Z",
                               "degraded_reason": "BROKER_OFFICE_HOURS_OFF"},
            "data_go_kr_bond_live": {"status": "passed", "bond_id": "114260",
                                     "as_of": "2026-05-16T00:00:00Z", "degraded_reason": None},
            "pykrx_fdr_cross_check": {"status": "passed", "day": "2026-05-15",
                                      "delta_bp": 0.0, "degraded_reason": None},
        },
        "token_consumption": {"azure_tokens_in": 100, "azure_tokens_out": 20},
        "evidence_paths": [],
    }


def _sod_json(*, violations: int = 0) -> dict:
    return {
        "status": "passed" if violations == 0 else "failed",
        "passed": violations == 0,
        "verified_at": "2026-05-16T00:00:00Z",
        "window": {"from": "2026-05-15T00:00:00Z", "to": "2026-05-16T00:00:00Z"},
        "buckets": {
            "poc_auto_approval": {"count": 5, "sample_audit_ids": []},
            "human_approved": {"count": 3, "sample_audit_ids": []},
            "violations": {"count": violations, "audit_ids": []},
        },
        "exception_list": [],
        "evidence_paths": [],
    }


def _write_full_case(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """Write a complete set of passing synthetic evidence files."""
    gate = tmp_path / "gate.md"
    svc = tmp_path / "serviceable.json"
    attest = tmp_path / "attestation.json"
    sod = tmp_path / "sod.json"
    result = tmp_path / "result.json"
    gate.write_text(_gate_report())
    svc.write_text(json.dumps(_serviceable_result()))
    attest.write_text(json.dumps(_attestation_json()))
    sod.write_text(json.dumps(_sod_json()))
    return gate, svc, attest, sod, result


def _base_args(
    gate: Path, svc: Path, attest: Path, sod: Path, result: Path
) -> list[str]:
    return [
        "--verification-gate-report", str(gate),
        "--serviceable-result-json", str(svc),
        "--result-json", str(result),
        "--skip-hostile-checks",
        "--skip-migrations",
        "--skip-gitleaks",
        "--attestation-json", str(attest),
        "--sod-evidence-json", str(sod),
    ]


# ── ADR-007 JSON triple compliance ────────────────────────────────────────────


def test_total_readiness_emits_adr007_triple(tmp_path: Path) -> None:
    """verify_total_product_readiness output must have {verified_at, status, passed,
    evidence_paths} at root — ADR-007 §0 cross-cutting invariant."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))

    assert rc == 0, f"expected exit 0, got {rc}"
    payload = json.loads(result.read_text())

    # ADR-007 §0 required keys
    assert "verified_at" in payload, "missing verified_at"
    assert "status" in payload, "missing status"
    assert "passed" in payload, "missing passed"
    assert "evidence_paths" in payload, "missing evidence_paths"
    assert isinstance(payload["evidence_paths"], list), "evidence_paths must be a list"
    # status and passed must be consistent
    assert payload["passed"] is True
    assert payload["status"] == "passed"


def test_external_research_emits_adr007_triple() -> None:
    """verify_external_research_application output must have ADR-007 §0 keys."""
    result_path = PROJECT_ROOT / ".omc" / "specs" / \
        "autoresearch-external-research-application" / "result.json"
    # Run against real project files
    rc = vera.main([
        "--backlog", str(PROJECT_ROOT / "BACKLOG.md"),
        "--regs", str(PROJECT_ROOT / "docs" / "regulations"),
        "--audit-codes-doc",
        str(PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"),
        "--out", str(result_path),
    ])

    assert rc in (0, 2), f"unexpected exit code {rc} (expected 0 or 2)"
    assert result_path.exists(), "result JSON not written"
    payload = json.loads(result_path.read_text())

    assert "verified_at" in payload, "missing verified_at"
    assert "status" in payload, "missing status"
    assert "passed" in payload, "missing passed"
    assert "evidence_paths" in payload, "missing evidence_paths"
    assert isinstance(payload["evidence_paths"], list)
    assert "summary" in payload
    assert "by_regulation" in payload


# ── Exit code contract (ADR-007 §0) ──────────────────────────────────────────


def test_total_readiness_exit_0_on_complete_evidence(tmp_path: Path) -> None:
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    assert rc == 0


def test_total_readiness_exit_2_on_failed_evidence(tmp_path: Path) -> None:
    """Any component failure → exit 2 (not 1)."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    attest.write_text(json.dumps(_attestation_json(passed=False)))
    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    assert rc == 2, f"expected exit 2 (ADR-007 fail), got {rc}"


def test_external_research_exit_0_on_real_files() -> None:
    """Full real-file run: all 120 REG task IDs map to BACKLOG → exit 0."""
    result_path = PROJECT_ROOT / ".omc" / "specs" / \
        "autoresearch-external-research-application" / "result.json"
    rc = vera.main([
        "--backlog", str(PROJECT_ROOT / "BACKLOG.md"),
        "--regs", str(PROJECT_ROOT / "docs" / "regulations"),
        "--audit-codes-doc",
        str(PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"),
        "--out", str(result_path),
    ])
    assert rc == 0, (
        f"verify_external_research_application exited {rc}; "
        "one or more REG task IDs unmapped from BACKLOG or missing golden tests"
    )
    payload = json.loads(result_path.read_text())
    assert payload["passed"] is True
    assert payload["summary"]["unmapped"] == [], \
        f"unmapped task IDs: {payload['summary']['unmapped']}"


def test_external_research_exit_3_on_missing_backlog(tmp_path: Path) -> None:
    """Missing BACKLOG → exit 3 (config error)."""
    with pytest.raises(SystemExit) as exc_info:
        vera.main([
            "--backlog", str(tmp_path / "missing-backlog.md"),
            "--regs", str(PROJECT_ROOT / "docs" / "regulations"),
            "--audit-codes-doc",
            str(PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"),
            "--out", str(tmp_path / "result.json"),
        ])
    assert exc_info.value.code == 3


def test_external_research_exit_3_on_missing_regs_dir(tmp_path: Path) -> None:
    """Missing regs dir → exit 3 (config error)."""
    with pytest.raises(SystemExit) as exc_info:
        vera.main([
            "--backlog", str(PROJECT_ROOT / "BACKLOG.md"),
            "--regs", str(tmp_path / "no-regs-here"),
            "--audit-codes-doc",
            str(PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"),
            "--out", str(tmp_path / "result.json"),
        ])
    assert exc_info.value.code == 3


# ── Aggregation component tests ───────────────────────────────────────────────


def test_total_readiness_fails_on_attestation_failure(tmp_path: Path) -> None:
    """Failed ext-dep attestation (azure status=failed) makes gate fail."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    bad_attest = _attestation_json(passed=False)
    bad_attest["deps"]["azure_gpt5_mini"]["status"] = "failed"
    attest.write_text(json.dumps(bad_attest))

    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    assert rc == 2
    payload = json.loads(result.read_text())
    assert payload["components"]["ext_dep_attestation"]["passed"] is False
    assert any(
        "azure_gpt5_mini" in err
        for err in payload["components"]["ext_dep_attestation"]["errors"]
    )


def test_total_readiness_fails_on_sod_violations(tmp_path: Path) -> None:
    """SoD evidence with violations count > 0 makes gate fail."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    sod.write_text(json.dumps(_sod_json(violations=3)))

    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    assert rc == 2
    payload = json.loads(result.read_text())
    assert payload["components"]["sod_evidence"]["passed"] is False
    assert any(
        "violations" in err.lower()
        for err in payload["components"]["sod_evidence"]["errors"]
    )


def test_total_readiness_reg_audit_codes_pass(tmp_path: Path) -> None:
    """All REG-01..REG-06 required audit codes must be present in OBS-02."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    payload = json.loads(result.read_text())
    comp = payload["components"]["reg_audit_codes"]
    assert comp["passed"] is True, f"REG audit codes missing: {comp.get('errors')}"
    assert comp["detail"]["missing_per_reg"] == {}


def test_total_readiness_dev_docs_exist(tmp_path: Path) -> None:
    """DEV-05..DEV-08 close-out docs must exist on disk."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    payload = json.loads(result.read_text())
    comp = payload["components"]["dev_docs_exist"]
    assert comp["passed"] is True, f"Dev docs missing: {comp.get('errors')}"


def test_total_readiness_module_split_diff_zero(tmp_path: Path) -> None:
    """All split submodules must be ≤ 500 lines (DEV-07 §2 budget)."""
    gate, svc, attest, sod, result = _write_full_case(tmp_path)
    rc = vtpr.main(_base_args(gate, svc, attest, sod, result))
    payload = json.loads(result.read_text())
    comp = payload["components"]["module_split_diff_zero"]
    assert comp["passed"] is True, (
        f"Oversized split submodules: {comp['detail'].get('oversized', [])}"
    )


# ── REG traceability per-regulation ───────────────────────────────────────────


@pytest.mark.parametrize("reg_name", ["REG-01", "REG-02", "REG-03", "REG-04", "REG-05", "REG-06"])
def test_external_research_reg_fully_traced(reg_name: str) -> None:
    """Every individual REG-NN must have 0 unmapped task IDs."""
    result_path = PROJECT_ROOT / ".omc" / "specs" / \
        "autoresearch-external-research-application" / "result.json"
    # Re-use cached result if it exists, otherwise run
    if not result_path.exists():
        vera.main([
            "--backlog", str(PROJECT_ROOT / "BACKLOG.md"),
            "--regs", str(PROJECT_ROOT / "docs" / "regulations"),
            "--audit-codes-doc",
            str(PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"),
            "--out", str(result_path),
        ])

    payload = json.loads(result_path.read_text())
    reg_result = payload["by_regulation"].get(reg_name)
    assert reg_result is not None, f"{reg_name} missing from result"
    assert reg_result["unmapped"] == [], \
        f"{reg_name} has unmapped task IDs: {reg_result['unmapped']}"
    assert reg_result["audit_code_missing"] == [], \
        f"{reg_name} has missing audit codes: {reg_result['audit_code_missing']}"
    assert reg_result["golden_tests_missing"] == [], \
        f"{reg_name} has missing golden tests: {reg_result['golden_tests_missing']}"


# ── CLI subprocess tests ───────────────────────────────────────────────────────


def test_external_research_cli_exit_0_real_files() -> None:
    """CLI invocation of verify_external_research_application exits 0 with real files."""
    result_path = PROJECT_ROOT / ".omc" / "specs" / \
        "autoresearch-external-research-application" / "cli-test-result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_external_research_application.py"),
            "--backlog", str(PROJECT_ROOT / "BACKLOG.md"),
            "--regs", str(PROJECT_ROOT / "docs" / "regulations"),
            "--audit-codes-doc",
            str(PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"),
            "--out", str(result_path),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, (
        f"CLI exited {completed.returncode}; stderr: {completed.stderr[:500]}"
    )
    payload = json.loads(result_path.read_text())
    assert payload["passed"] is True
    # ADR-007 triple present in stdout JSON
    stdout_payload = json.loads(completed.stdout.strip())
    assert "verified_at" in stdout_payload
    assert "evidence_paths" in stdout_payload


def test_total_readiness_cli_exit_2_on_missing_artifacts(tmp_path: Path) -> None:
    """CLI: missing gate report → exit 2 (ADR-007 failure code)."""
    result_path = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_total_product_readiness.py"),
            "--verification-gate-report", str(tmp_path / "no-gate.md"),
            "--serviceable-result-json", str(tmp_path / "no-svc.json"),
            "--result-json", str(result_path),
            "--skip-hostile-checks",
            "--skip-migrations",
            "--skip-gitleaks",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 2, (
        f"expected exit 2, got {completed.returncode}"
    )
    payload = json.loads(result_path.read_text())
    assert payload["passed"] is False
    assert "verified_at" in payload  # ADR-007 triple even on failure
    assert "evidence_paths" in payload
