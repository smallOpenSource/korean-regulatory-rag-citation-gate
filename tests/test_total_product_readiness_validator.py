"""Total-product readiness validator false-green contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import verify_total_product_readiness as total_ready

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _gate_report(*, omit_step: str | None = None, failed_step: str | None = None) -> str:
    lines = [
        "# Verification Gate Evidence",
        "",
        "- started_at_utc: 2026-05-16T00:00:00Z",
        "- harness_root: .",
        "- python: /opt/conda/envs/wm_env/bin/python",
    ]
    for name in (*total_ready.REQUIRED_GATE_STEPS, *total_ready.DIAGNOSTIC_GATE_STEPS):
        if name == omit_step:
            continue
        status = 7 if name == failed_step else 0
        diagnostic = (
            "; non-blocking diagnostic"
            if name in total_ready.DIAGNOSTIC_GATE_STEPS
            else ""
        )
        lines.extend(
            [
                "",
                f"## {name}",
                "",
                "```console",
                f"$ echo {name}",
                "SUCCESS but exit status is authoritative" if status else "ok",
                f"(exit {status}{diagnostic})",
                "```",
            ]
        )
    lines.extend(["", "## Summary", "", "- finished_at_utc: 2026-05-16T00:01:00Z", "- failures: 0"])
    return "\n".join(lines) + "\n"


def _serviceable_result(*, passed: bool = True) -> dict[str, object]:
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "verifier_signoff": "serviceable-readiness-validator" if passed else None,
        "selected_count": 200,
        "coverage_ratio": 1.0,
        "readiness": {
            "coverage": {
                "selected_count": 200,
                "coverage_ratio": 1.0,
                "missing_member_days": 0,
            }
        },
    }


def _synthetic_attestation() -> dict[str, object]:
    """Minimal passing external-dependency-attestation payload."""
    return {
        "status": "passed",
        "passed": True,
        "verified_at": "2026-05-16T00:00:00Z",
        "window": {"start": "2026-05-15T00:00:00Z", "end": "2026-05-16T00:00:00Z"},
        "env_profile": "poc",
        "deps": {
            "azure_gpt5_mini": {"status": "passed", "agent_calls": [], "degraded_reason": None},
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


def _synthetic_sod_evidence() -> dict[str, object]:
    """Minimal passing SoD evidence pack payload."""
    return {
        "status": "passed",
        "passed": True,
        "verified_at": "2026-05-16T00:00:00Z",
        "window": {"from": "2026-05-15T00:00:00Z", "to": "2026-05-16T00:00:00Z"},
        "buckets": {
            "poc_auto_approval": {"count": 5, "sample_audit_ids": []},
            "human_approved": {"count": 3, "sample_audit_ids": []},
            "violations": {"count": 0, "audit_ids": []},
        },
        "exception_list": [],
        "evidence_paths": [],
    }


def _write_case(
    tmp_path: Path,
    *,
    gate_text: str | None = None,
    serviceable: dict[str, object] | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    """Write synthetic evidence files and return their paths."""
    gate_path = tmp_path / "gate.md"
    serviceable_path = tmp_path / "serviceable-result.json"
    result_path = tmp_path / "total-result.json"
    attestation_path = tmp_path / "external-dependency-attestation.json"
    sod_path = tmp_path / "sod-evidence-pack.json"
    gate_path.write_text(gate_text if gate_text is not None else _gate_report())
    serviceable_path.write_text(json.dumps(serviceable or _serviceable_result()))
    attestation_path.write_text(json.dumps(_synthetic_attestation()))
    sod_path.write_text(json.dumps(_synthetic_sod_evidence()))
    return gate_path, serviceable_path, result_path, attestation_path, sod_path


def _aggregator_skip_flags(
    tmp_path: Path,
    attestation_path: Path,
    sod_path: Path,
    result_path: Path,
    gate_path: Path,
    serviceable_path: Path,
) -> list[str]:
    """Build CLI arg list with aggregation skip flags for unit tests."""
    return [
        "--verification-gate-report", str(gate_path),
        "--serviceable-result-json", str(serviceable_path),
        "--result-json", str(result_path),
        "--skip-hostile-checks",
        "--skip-migrations",   # no live PG17 in unit tests
        "--skip-gitleaks",     # gitleaks binary not required in unit tests
        "--attestation-json", str(attestation_path),
        "--sod-evidence-json", str(sod_path),
    ]


def test_total_product_validator_passes_complete_evidence(tmp_path: Path) -> None:
    gate_path, serviceable_path, result_path, attestation_path, sod_path = _write_case(tmp_path)

    status = total_ready.main(
        _aggregator_skip_flags(tmp_path, attestation_path, sod_path,
                               result_path, gate_path, serviceable_path)
    )

    assert status == 0
    payload = json.loads(result_path.read_text())
    assert payload["status"] == "passed"
    assert payload["passed"] is True
    # ADR-007 compliance: verified_at and evidence_paths present
    assert "verified_at" in payload
    assert isinstance(payload["evidence_paths"], list)
    assert payload["components"]["verification_gate"]["passed"] is True
    assert payload["components"]["serviceable_readiness"]["detail"]["selected_count"] == 200
    # New aggregation components
    assert payload["components"]["module_split_diff_zero"]["passed"] is True
    assert payload["components"]["ext_dep_attestation"]["passed"] is True
    assert payload["components"]["sod_evidence"]["passed"] is True
    assert payload["components"]["reg_audit_codes"]["passed"] is True
    assert payload["components"]["dev_docs_exist"]["passed"] is True


def test_total_product_validator_rejects_missing_e2e_even_with_zero_failures(
    tmp_path: Path,
) -> None:
    gate_path, serviceable_path, result_path, attestation_path, sod_path = _write_case(
        tmp_path,
        gate_text=_gate_report(omit_step="Playwright E2E"),
    )

    status = total_ready.main(
        _aggregator_skip_flags(tmp_path, attestation_path, sod_path,
                               result_path, gate_path, serviceable_path)
    )

    assert status == 2  # ADR-007 exit code 2 = validation failure
    payload = json.loads(result_path.read_text())
    assert any(
        "missing required verification step: Playwright E2E" in error
        for error in payload["errors"]
    )


def test_total_product_validator_rejects_misleading_success_exit_status(tmp_path: Path) -> None:
    gate_path, serviceable_path, result_path, attestation_path, sod_path = _write_case(
        tmp_path,
        gate_text=_gate_report(failed_step="Pytest"),
    )

    status = total_ready.main(
        _aggregator_skip_flags(tmp_path, attestation_path, sod_path,
                               result_path, gate_path, serviceable_path)
    )

    assert status == 2  # ADR-007 exit code 2 = validation failure
    payload = json.loads(result_path.read_text())
    assert any("verification step Pytest exited 7" in error for error in payload["errors"])


def test_total_product_validator_rejects_failed_serviceable_result(tmp_path: Path) -> None:
    gate_path, serviceable_path, result_path, attestation_path, sod_path = _write_case(
        tmp_path,
        serviceable=_serviceable_result(passed=False),
    )

    status = total_ready.main(
        _aggregator_skip_flags(tmp_path, attestation_path, sod_path,
                               result_path, gate_path, serviceable_path)
    )

    assert status == 2  # ADR-007 exit code 2 = validation failure
    payload = json.loads(result_path.read_text())
    assert any(
        "serviceable readiness result must have passed=true" in error
        for error in payload["errors"]
    )


def test_total_product_validator_cli_writes_failed_result_for_missing_artifacts(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "missing-result.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_total_product_readiness.py"),
            "--verification-gate-report",
            str(tmp_path / "missing-gate.md"),
            "--serviceable-result-json",
            str(tmp_path / "missing-serviceable.json"),
            "--result-json",
            str(result_path),
            "--skip-hostile-checks",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    # ADR-007 exit code 2 = validation failure (changed from 1 in aggregator update)
    assert completed.returncode == 2
    payload = json.loads(result_path.read_text())
    assert payload["passed"] is False
    assert any("missing artifact" in error for error in payload["errors"])


def test_total_product_validator_is_documented_in_test_strategy_and_deploy_runbook() -> None:
    docs_text = (PROJECT_ROOT / "docs" / "test" / "TEST-01_test_strategy.md").read_text()
    deploy_text = (PROJECT_ROOT / "docs" / "runbooks" / "OPS-02_deploy.md").read_text()

    assert "scripts/verify_total_product_readiness.py" in docs_text
    assert "total-product readiness" in docs_text
    assert "scripts/verify_total_product_readiness.py" in deploy_text
    assert "false-green" in docs_text + deploy_text
