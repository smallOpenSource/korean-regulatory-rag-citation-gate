"""Batch scheduler governance and refresh-control contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from apps.api.harness.batch import runner, scheduler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_BIN = os.environ.get("PYTHON_PATH", sys.executable)


def _base_env() -> dict[str, str]:
    return {
        "HARNESS_BATCH_SCHEDULER_ENABLED": "true",
        "HARNESS_PROVIDER_STRICTNESS": "required",
        "HARNESS_BATCH_LOOKBACK_DAYS": "30",
        "HARNESS_BATCH_AS_OF_DATE": "2026-05-16",
    }


def test_default_scheduler_plan_exposes_rag_and_derived_refresh_controls() -> None:
    plan = scheduler.scheduler_plan(_base_env())
    jobs = {job["name"]: job for job in plan["jobs"]}

    assert jobs["rag_refresh"]["runnable"] is True
    assert jobs["rag_refresh"]["stages"] == ["transform", "embed"]
    assert jobs["derived_refresh"]["runnable"] is True
    assert jobs["derived_refresh"]["stages"] == ["derived", "house-view"]
    assert jobs["serviceable_top200_30d"]["enabled"] is False
    assert plan["provider_strictness_values"] == ["all", "required"]


def test_serviceable_scheduler_blocks_non_official_krx_top200_fallback() -> None:
    env = {
        **_base_env(),
        "HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED": "true",
        "HARNESS_BATCH_KRX_ENABLED": "true",
        "HARNESS_BATCH_KRX_SOURCE": "PYKRX",
        "HARNESS_BATCH_KRX_POLICY": "PYKRX_AUXILIARY_APPROVED",
        "HARNESS_BATCH_KRX_UNIVERSE_CODE": "DOMESTIC_TOP200_MARKET_CAP",
        "HARNESS_BATCH_KRX_UNIVERSE_SIZE": "200",
        "HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO": "1.0",
    }

    serviceable_job = {
        job.name: job for job in scheduler.resolve_scheduler_jobs(env)
    }["serviceable_top200_30d"]

    assert serviceable_job.enabled is True
    assert serviceable_job.runnable is False
    assert any("no PYKRX fallback" in reason for reason in serviceable_job.blocked_reasons)


def test_serviceable_scheduler_accepts_only_complete_official_top200_governance() -> None:
    env = {
        **_base_env(),
        "HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED": "true",
        "HARNESS_BATCH_KRX_ENABLED": "true",
        "HARNESS_BATCH_KRX_SOURCE": "KRX",
        "HARNESS_BATCH_KRX_POLICY": "OFFICIAL_KRX_APPROVED",
        "KRX_API_BASE_URL": "https://data-dbg.krx.co.kr",
        "KRX_API_KEY": "unit-test-secret",
        "HARNESS_BATCH_KRX_UNIVERSE_CODE": "DOMESTIC_TOP200_MARKET_CAP",
        "HARNESS_BATCH_KRX_UNIVERSE_SIZE": "200",
        "HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO": "1.0",
    }

    serviceable_job = {
        job.name: job for job in scheduler.resolve_scheduler_jobs(env)
    }["serviceable_top200_30d"]

    assert serviceable_job.runnable is True
    assert serviceable_job.stages == runner.DEFAULT_STAGES
    assert serviceable_job.provider_strictness == "required"
    assert serviceable_job.as_dict()["blocked_reasons"] == []


def test_custom_scheduler_jobs_require_global_gate_and_validate_stages() -> None:
    env = {
        "HARNESS_BATCH_SCHEDULER_ENABLED": "false",
        "HARNESS_BATCH_SCHEDULES_JSON": json.dumps(
            [
                {
                    "name": "custom_rag",
                    "stages": ["transform", "embed"],
                    "interval_seconds": 120,
                    "provider_strictness": "required",
                }
            ]
        ),
    }

    jobs = scheduler.resolve_scheduler_jobs(env)

    assert len(jobs) == 1
    assert jobs[0].name == "custom_rag"
    assert jobs[0].enabled is False
    assert jobs[0].runnable is False
    assert "HARNESS_BATCH_SCHEDULER_ENABLED" in jobs[0].blocked_reasons[0]


def test_provider_governance_matrix_preserves_official_krx_precedence() -> None:
    governance = runner.provider_governance_matrix()
    krx = next(entry for entry in governance if entry["provider_code"] == "KRX")

    official, auxiliary = krx["source_branches"]
    assert official["source_code"] == "KRX"
    assert official["source_policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert official["may_satisfy_official_top200_30d"] is True
    assert official["fallback_behavior"] == "fail_closed_no_pykrx_auto_fallback"
    assert auxiliary["source_code"] == "PYKRX"
    assert auxiliary["source_official"] is False
    assert auxiliary["may_satisfy_official_top200_30d"] is False
    assert krx["official_top200_30d_gate"] == {
        "universe_code": "DOMESTIC_TOP200_MARKET_CAP",
        "minimum_selected_count": 200,
        "required_coverage_ratio": 1.0,
        "required_missing_member_days": 0,
        "required_source_code": "KRX",
        "required_source_policy_code": "OFFICIAL_KRX_APPROVED",
    }
    assert "unit-test-secret" not in str(governance)


def test_scheduler_plan_cli_is_secret_safe(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HARNESS_BATCH_SCHEDULER_ENABLED=true",
                "HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED=true",
                "HARNESS_BATCH_KRX_ENABLED=true",
                "HARNESS_BATCH_KRX_SOURCE=KRX",
                "HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED",
                "KRX_API_BASE_URL=https://data-dbg.krx.co.kr",
                "KRX_API_KEY=unit-test-scheduler-secret",
                "HARNESS_BATCH_KRX_UNIVERSE_CODE=DOMESTIC_TOP200_MARKET_CAP",
                "HARNESS_BATCH_KRX_UNIVERSE_SIZE=200",
                "HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO=1.0",
            ]
        )
        + "\n"
    )

    result = subprocess.run(
        [
            PYTHON_BIN,
            "scripts/run_batch_scheduler.py",
            "--plan-only",
            "--env-file",
            str(env_file),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env={"PYTHONPATH": f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "unit-test-scheduler-secret" not in result.stdout
    payload = json.loads(result.stdout)
    serviceable = next(job for job in payload["jobs"] if job["name"] == "serviceable_top200_30d")
    assert serviceable["runnable"] is True
    assert payload["provider_governance"]
