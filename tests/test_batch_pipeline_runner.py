"""Batch pipeline runner and verification-script contract checks."""

from __future__ import annotations

import importlib
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from db.migrator import validate_statement

PROJECT_ROOT = Path(__file__).resolve().parents[1]
runner = importlib.import_module("apps.api.harness.batch.runner")


@contextmanager
def temporary_env(updates: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_batch_runner_stage_parser_defaults_and_rejects_unknown_stage():
    assert runner.parse_stage_list(None) == runner.DEFAULT_STAGES
    assert runner.parse_stage_list("seed,provider,transform") == (
        "seed",
        "provider",
        "transform",
    )

    with pytest.raises(ValueError, match="Unsupported batch stage"):
        runner.parse_stage_list("seed,pretend-async")


def test_batch_runner_postcondition_sql_has_sql_ids():
    for name, statement in runner.POSTCONDITION_SQL.items():
        validate_statement(statement, context=f"runner.POSTCONDITION_SQL[{name}]")


def test_batch_runner_missing_env_helper_reports_blank_values():
    updates = {
        "BATCH_TEST_PRESENT": "value",
        "BATCH_TEST_BLANK": "   ",
        "BATCH_TEST_ABSENT": None,
    }
    with temporary_env(updates):
        assert runner.missing_env(
            ("BATCH_TEST_PRESENT", "BATCH_TEST_BLANK", "BATCH_TEST_ABSENT")
        ) == ["BATCH_TEST_BLANK", "BATCH_TEST_ABSENT"]


def test_batch_runner_script_exposes_required_cli_surface():
    script = PROJECT_ROOT / "scripts" / "run_batch_pipeline.sh"
    text = script.read_text()

    assert "apps/api/harness/batch/runner.py" in text
    assert "--profile" in subprocess.run(
        [str(script), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}",
        },
    ).stdout
    assert "--strict-external" in subprocess.run(
        [str(script), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}",
        },
    ).stdout


def test_provider_smoke_script_runs_external_smoke_with_strict_skip_gate():
    script = PROJECT_ROOT / "scripts" / "provider_smoke.sh"
    text = script.read_text()

    assert "tests/test_external_clients_smoke.py" in text
    assert "--strict-external" in text
    assert "SKIPPED/BLOCKED_WITH_REDACTED_REASON" in text


def test_provider_discovery_script_exposes_ecos_parseable_row_gate():
    script = PROJECT_ROOT / "scripts" / "provider_discovery.sh"
    text = script.read_text()

    assert "apps.api.harness.batch.ecos_discovery" in text
    assert "--provider" in text
    assert "ecos)" in text
    assert "--min-parseable-targets" in subprocess.run(
        [str(script), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}",
        },
    ).stdout


def test_verification_gate_script_keeps_e2e_and_batch_reproducible():
    script_text = (PROJECT_ROOT / "scripts" / "run_verification_gate.sh").read_text()

    required_fragments = [
        "scripts/status.sh --deep --no-fail",
        "ruff check apps/api db tests",
        "pytest -q",
        "npm run typecheck",
        "npm run lint",
        "npm run test -- --run",
        "npm run build",
        "npm run e2e",
        "scripts/run_batch_pipeline.sh",
        "--all-stages",
    ]
    for fragment in required_fragments:
        assert fragment in script_text
