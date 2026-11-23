"""Dependency-free batch scheduler control surface.

The production deployment docs describe a scheduler service, but the safe local
operator contract is still the existing batch runner with Redis locks and
batch_job_logs.  This module adds a small, testable scheduler plan around that
runner without introducing an implicit APScheduler dependency or a background
process at import time.
"""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.batch.runner import (
    DEFAULT_BATCH_LOOKBACK_DAYS,
    DEFAULT_STAGES,
    OFFICIAL_KRX_POLICY_CODE,
    OFFICIAL_KRX_SOURCE_CODE,
    PROVIDER_STRICTNESS_REQUIRED,
    PROVIDER_STRICTNESS_VALUES,
    env_date_value,
    normalize_provider_strictness,
    parse_stage_list,
    provider_governance_matrix,
    run_pipeline,
)
from apps.api.harness.core.config import load_env_file
from apps.api.harness.core.logging import redact_secret_text

SCHEDULER_SCHEMA_VERSION = "1.0"
GLOBAL_SCHEDULER_ENV = "HARNESS_BATCH_SCHEDULER_ENABLED"
CUSTOM_SCHEDULES_ENV = "HARNESS_BATCH_SCHEDULES_JSON"
SERVICEABLE_UNIVERSE_CODE = "DOMESTIC_TOP200_MARKET_CAP"
DEFAULT_RAG_REFRESH_STAGES = ("transform", "embed")
DEFAULT_DERIVED_REFRESH_STAGES = ("derived", "house-view")
DEFAULT_SERVICEABLE_TOP200_STAGES = DEFAULT_STAGES
DEFAULT_SCHEDULE_REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "batch" / "scheduled"


@dataclass(frozen=True)
class ScheduledBatchJob:
    """One scheduler-managed batch runner invocation."""

    name: str
    stages: tuple[str, ...]
    interval_seconds: int
    enabled: bool
    profile: str = "full-mvp"
    report_path: Path | None = None
    lookback_days: int = DEFAULT_BATCH_LOOKBACK_DAYS
    as_of_date: date | None = None
    provider_strictness: str = PROVIDER_STRICTNESS_REQUIRED
    requires_official_top200: bool = False
    blocked_reasons: tuple[str, ...] = ()

    @property
    def runnable(self) -> bool:
        """Return whether the scheduler may execute this job."""

        return self.enabled and not self.blocked_reasons

    def resolved_report_path(self, report_dir: Path) -> Path:
        """Return the report path for this job inside the caller's report directory."""

        if self.report_path is not None:
            return self.report_path
        return report_dir / f"{self.name}-latest.json"

    def as_dict(self, *, report_dir: Path | None = None) -> dict[str, Any]:
        """Serialize without leaking environment values."""

        payload: dict[str, Any] = {
            "name": self.name,
            "stages": list(self.stages),
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "runnable": self.runnable,
            "profile": self.profile,
            "lookback_days": self.lookback_days,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "provider_strictness": self.provider_strictness,
            "requires_official_top200": self.requires_official_top200,
            "blocked_reasons": list(self.blocked_reasons),
        }
        if report_dir is not None:
            payload["report_path"] = str(self.resolved_report_path(report_dir))
        elif self.report_path is not None:
            payload["report_path"] = str(self.report_path)
        return payload


def _mapping_get(env: dict[str, str], name: str) -> str:
    return str(env.get(name, "")).strip()


def _env_bool_from_mapping(env: dict[str, str], name: str, *, default: bool = False) -> bool:
    text = _mapping_get(env, name).lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _env_int_from_mapping(
    env: dict[str, str],
    name: str,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    text = _mapping_get(env, name)
    if not text:
        value = default
    else:
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _env_float_from_mapping(env: dict[str, str], name: str, *, default: float) -> float:
    text = _mapping_get(env, name)
    if not text:
        return default
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def _env_date_from_mapping(env: dict[str, str], name: str) -> date | None:
    text = _mapping_get(env, name)
    if not text:
        return None
    return env_date_value(text, field_name=name)


def _official_top200_blockers(env: dict[str, str]) -> tuple[str, ...]:
    """Return fail-closed reasons before a serviceable top-200 scheduled run."""

    blockers: list[str] = []
    if not _env_bool_from_mapping(env, "HARNESS_BATCH_KRX_ENABLED", default=False):
        blockers.append("HARNESS_BATCH_KRX_ENABLED must be true for serviceable official KRX runs")
    if _mapping_get(env, "HARNESS_BATCH_KRX_SOURCE").upper() != OFFICIAL_KRX_SOURCE_CODE:
        blockers.append("HARNESS_BATCH_KRX_SOURCE must be KRX; no PYKRX fallback is allowed")
    if _mapping_get(env, "HARNESS_BATCH_KRX_POLICY").upper() != OFFICIAL_KRX_POLICY_CODE:
        blockers.append("HARNESS_BATCH_KRX_POLICY must be OFFICIAL_KRX_APPROVED")
    missing = [name for name in ("KRX_API_BASE_URL", "KRX_API_KEY") if not _mapping_get(env, name)]
    if missing:
        blockers.append(f"official KRX env is missing: {', '.join(missing)}")
    if _mapping_get(env, "HARNESS_BATCH_KRX_UNIVERSE_CODE") != SERVICEABLE_UNIVERSE_CODE:
        blockers.append("HARNESS_BATCH_KRX_UNIVERSE_CODE must be DOMESTIC_TOP200_MARKET_CAP")
    universe_size = _env_int_from_mapping(
        env,
        "HARNESS_BATCH_KRX_UNIVERSE_SIZE",
        default=0,
        minimum=0,
    )
    if universe_size < 200:
        blockers.append("HARNESS_BATCH_KRX_UNIVERSE_SIZE must be >= 200")
    coverage_ratio = _env_float_from_mapping(
        env,
        "HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO",
        default=0.0,
    )
    if coverage_ratio < 1.0:
        blockers.append("HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO must be >= 1.0")
    return tuple(blockers)


def _job_from_mapping(
    raw: dict[str, Any],
    *,
    env: dict[str, str],
    global_enabled: bool,
) -> ScheduledBatchJob:
    """Parse one JSON schedule object into a safe job definition."""

    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("Each schedule job requires a non-empty name")
    stages_value = raw.get("stages")
    stages = parse_stage_list(
        ",".join(stages_value) if isinstance(stages_value, list) else str(stages_value or "all"),
        all_stages=bool(raw.get("all_stages", False)),
    )
    provider_strictness = normalize_provider_strictness(
        str(raw.get("provider_strictness") or PROVIDER_STRICTNESS_REQUIRED)
    )
    enabled = global_enabled and bool(raw.get("enabled", True))
    interval_seconds = int(raw.get("interval_seconds") or 3600)
    if interval_seconds < 1:
        raise ValueError(f"{name}.interval_seconds must be >= 1")
    lookback_days = int(raw.get("lookback_days") or DEFAULT_BATCH_LOOKBACK_DAYS)
    if lookback_days < 1:
        raise ValueError(f"{name}.lookback_days must be >= 1")
    requires_official_top200 = bool(raw.get("requires_official_top200", False))
    blocked_reasons = _official_top200_blockers(env) if requires_official_top200 else ()
    if not global_enabled:
        blocked_reasons = (f"{GLOBAL_SCHEDULER_ENV} is not true", *blocked_reasons)
    report_path = Path(str(raw["report_path"])) if raw.get("report_path") else None
    as_of_date = None
    if raw.get("as_of_date"):
        as_of_date = env_date_value(str(raw["as_of_date"]), field_name=f"{name}.as_of_date")
    return ScheduledBatchJob(
        name=name,
        stages=stages,
        interval_seconds=interval_seconds,
        enabled=enabled,
        profile=str(raw.get("profile") or "full-mvp"),
        report_path=report_path,
        lookback_days=lookback_days,
        as_of_date=as_of_date,
        provider_strictness=provider_strictness,
        requires_official_top200=requires_official_top200,
        blocked_reasons=blocked_reasons,
    )


def _default_jobs(env: dict[str, str], *, global_enabled: bool) -> tuple[ScheduledBatchJob, ...]:
    """Build the documented built-in scheduler jobs."""

    global_blocker = () if global_enabled else (f"{GLOBAL_SCHEDULER_ENV} is not true",)
    common_as_of_date = _env_date_from_mapping(env, "HARNESS_BATCH_AS_OF_DATE")
    provider_strictness = normalize_provider_strictness(
        _mapping_get(env, "HARNESS_PROVIDER_STRICTNESS") or PROVIDER_STRICTNESS_REQUIRED
    )
    lookback_days = _env_int_from_mapping(
        env,
        "HARNESS_BATCH_LOOKBACK_DAYS",
        default=DEFAULT_BATCH_LOOKBACK_DAYS,
        minimum=1,
    )
    serviceable_enabled = global_enabled and _env_bool_from_mapping(
        env,
        "HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED",
        default=False,
    )
    serviceable_blockers = _official_top200_blockers(env) if serviceable_enabled else ()

    return (
        ScheduledBatchJob(
            name="rag_refresh",
            stages=DEFAULT_RAG_REFRESH_STAGES,
            interval_seconds=_env_int_from_mapping(
                env,
                "HARNESS_BATCH_RAG_REFRESH_INTERVAL_SECONDS",
                default=3600,
                minimum=60,
            ),
            enabled=global_enabled
            and _env_bool_from_mapping(env, "HARNESS_BATCH_RAG_REFRESH_ENABLED", default=True),
            lookback_days=lookback_days,
            as_of_date=common_as_of_date,
            provider_strictness=provider_strictness,
            blocked_reasons=global_blocker,
        ),
        ScheduledBatchJob(
            name="derived_refresh",
            stages=DEFAULT_DERIVED_REFRESH_STAGES,
            interval_seconds=_env_int_from_mapping(
                env,
                "HARNESS_BATCH_DERIVED_REFRESH_INTERVAL_SECONDS",
                default=3600,
                minimum=60,
            ),
            enabled=global_enabled
            and _env_bool_from_mapping(env, "HARNESS_BATCH_DERIVED_REFRESH_ENABLED", default=True),
            lookback_days=lookback_days,
            as_of_date=common_as_of_date,
            provider_strictness=provider_strictness,
            blocked_reasons=global_blocker,
        ),
        ScheduledBatchJob(
            name="serviceable_top200_30d",
            stages=DEFAULT_SERVICEABLE_TOP200_STAGES,
            interval_seconds=_env_int_from_mapping(
                env,
                "HARNESS_BATCH_SERVICEABLE_TOP200_INTERVAL_SECONDS",
                default=24 * 60 * 60,
                minimum=3600,
            ),
            enabled=serviceable_enabled,
            lookback_days=30,
            as_of_date=common_as_of_date,
            provider_strictness=PROVIDER_STRICTNESS_REQUIRED,
            requires_official_top200=True,
            blocked_reasons=(global_blocker + serviceable_blockers),
        ),
    )


def resolve_scheduler_jobs(env: dict[str, str] | None = None) -> tuple[ScheduledBatchJob, ...]:
    """Resolve scheduler jobs from env without exposing secret values."""

    resolved_env = dict(os.environ if env is None else env)
    global_enabled = _env_bool_from_mapping(resolved_env, GLOBAL_SCHEDULER_ENV, default=False)
    raw_custom = _mapping_get(resolved_env, CUSTOM_SCHEDULES_ENV)
    if raw_custom:
        try:
            custom_items = json.loads(raw_custom)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{CUSTOM_SCHEDULES_ENV} must be valid JSON") from exc
        if not isinstance(custom_items, list):
            raise ValueError(f"{CUSTOM_SCHEDULES_ENV} must be a JSON list")
        return tuple(
            _job_from_mapping(item, env=resolved_env, global_enabled=global_enabled)
            for item in custom_items
            if isinstance(item, dict)
        )
    return _default_jobs(resolved_env, global_enabled=global_enabled)


def scheduler_plan(
    env: dict[str, str] | None = None, *, report_dir: Path | None = None
) -> dict[str, Any]:
    """Return an operator-safe scheduler and provider-governance plan."""

    jobs = resolve_scheduler_jobs(env)
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "scheduler_enabled": any(job.enabled for job in jobs),
        "global_gate_env": GLOBAL_SCHEDULER_ENV,
        "custom_schedules_env": CUSTOM_SCHEDULES_ENV,
        "provider_strictness_values": sorted(PROVIDER_STRICTNESS_VALUES),
        "jobs": [
            job.as_dict(report_dir=report_dir or DEFAULT_SCHEDULE_REPORT_DIR) for job in jobs
        ],
        "provider_governance": provider_governance_matrix(),
    }


async def run_scheduler_once(
    *,
    env_path: Path,
    report_dir: Path = DEFAULT_SCHEDULE_REPORT_DIR,
    job_filter: str | None = None,
) -> dict[str, Any]:
    """Run runnable scheduler jobs once and return summarized evidence.

    Args:
        env_path: Path to the .env file to load before running.
        report_dir: Directory for per-job report files.
        job_filter: When set, run only the job with this name; otherwise run all.
    """

    load_env_file(env_path)
    all_jobs = resolve_scheduler_jobs()
    jobs = tuple(j for j in all_jobs if job_filter is None or j.name == job_filter)
    job_results: list[dict[str, Any]] = []
    for job in jobs:
        evidence = job.as_dict(report_dir=report_dir)
        if not job.enabled:
            job_results.append({**evidence, "run_status": "SKIPPED_DISABLED"})
            continue
        if job.blocked_reasons:
            job_results.append({**evidence, "run_status": "BLOCKED"})
            continue
        try:
            report = await run_pipeline(
                profile=job.profile,
                stages=job.stages,
                report_path=job.resolved_report_path(report_dir),
                env_path=env_path,
                embedding_batch_size=None,
                strict_external=None,
                lookback_days=job.lookback_days,
                as_of_date=job.as_of_date,
                provider_strictness=job.provider_strictness,
            )
        except Exception as exc:  # noqa: BLE001 - sanitize operator-facing scheduler result
            job_results.append(
                {
                    **evidence,
                    "run_status": "FAILED",
                    "error_message": redact_secret_text(str(exc)),
                }
            )
            continue
        job_results.append(
            {
                **evidence,
                "run_status": "DONE" if report.get("ok") else "DEGRADED",
                "exit_code": report.get("exit_code"),
                "status_code": report.get("status_code"),
                "local_status_code": report.get("local_status_code"),
                "provider_required_status_code": report.get("provider_required_status_code"),
            }
        )
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "jobs": job_results,
        "ok": all(item["run_status"] in {"DONE", "SKIPPED_DISABLED"} for item in job_results),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or inspect Harness batch scheduler jobs.")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_SCHEDULE_REPORT_DIR)
    parser.add_argument("--plan-only", action="store_true", help="Print scheduler plan and exit.")
    parser.add_argument(
        "--run-once",
        nargs="?",
        const="__all__",
        default=None,
        metavar="JOB_NAME",
        help="Run scheduler jobs once. Optionally name a job to run only that one.",
    )
    parser.add_argument(
        "--apscheduler",
        action="store_true",
        help=(
            "Start APScheduler cron daemon (requires HARNESS_BATCH_APSCHEDULER_ENABLED=true "
            "and at least one CRON_BATCH_* env var). Disabled by default."
        ),
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Loop count for scheduler service mode; requires --run-once or --plan-only=false.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=60,
        help="Sleep between iterations when max-iterations is greater than one.",
    )
    return parser.parse_args(argv)


# ═══════════════════════════════════════════════════════════════════════════════
# APScheduler cron-expression stub (Task W3-T5 — DISABLED by default)
#
# Activate with HARNESS_BATCH_APSCHEDULER_ENABLED=true + CRON_BATCH_* env vars.
# See docs/runbooks/RUN-09_batch_scheduler.md for full operator guide.
# ═══════════════════════════════════════════════════════════════════════════════

APSCHEDULER_GATE_ENV = "HARNESS_BATCH_APSCHEDULER_ENABLED"

# Cron-expression env vars → job name mapping (all empty/disabled by default)
CRON_ENV_MAP: dict[str, str] = {
    "rag_refresh":            "CRON_BATCH_RAG_REFRESH",
    "derived_refresh":        "CRON_BATCH_DERIVED_REFRESH",
    "serviceable_top200_30d": "CRON_BATCH_SERVICEABLE_TOP200",
    "house_view":             "CRON_BATCH_HOUSE_VIEW",
}


def _apscheduler_cron_map(env: dict[str, str]) -> dict[str, str]:
    """Return {job_name: cron_expression} for configured CRON_BATCH_* env vars."""
    return {
        job: expr
        for job, key in CRON_ENV_MAP.items()
        if (expr := env.get(key, "").strip())
    }


def run_with_apscheduler(
    *,
    env_path: Path,
    report_dir: Path = DEFAULT_SCHEDULE_REPORT_DIR,
) -> None:
    """Start APScheduler blocking daemon with env-configured cron expressions.

    DISABLED by default — requires ``HARNESS_BATCH_APSCHEDULER_ENABLED=true``
    and at least one ``CRON_BATCH_*`` env var set to a 5-field cron expression.

    This function blocks the calling process (APScheduler.start()).
    For PoC demo, run in a supervised tmux pane or background process.

    Raises:
        RuntimeError: when gate env is false or apscheduler is not installed.
    """
    resolved_env = dict(os.environ)
    if not _env_bool_from_mapping(resolved_env, APSCHEDULER_GATE_ENV, default=False):
        raise RuntimeError(
            f"APScheduler daemon is disabled. Set {APSCHEDULER_GATE_ENV}=true to enable."
        )

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler  # pyright: ignore[reportMissingImports]
        from apscheduler.triggers.cron import CronTrigger  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise RuntimeError(
            "apscheduler package is required: pip install 'apscheduler>=3.10'"
        ) from exc

    cron_map = _apscheduler_cron_map(resolved_env)
    if not cron_map:
        raise RuntimeError(
            "No CRON_BATCH_* env vars configured. "
            "Set at least one cron expression (e.g. CRON_BATCH_RAG_REFRESH='0 9 * * 1-5')."
        )

    scheduler: Any = BlockingScheduler(timezone="Asia/Seoul")

    for job_name, cron_expr in cron_map.items():
        parts = cron_expr.split()
        if len(parts) != 5:  # noqa: PLR2004
            print(
                f"[WARN] Skipping {job_name!r}: invalid cron {cron_expr!r} (need 5 fields)",
                file=sys.stderr,
            )
            continue
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day, month=month,
            day_of_week=day_of_week, timezone="Asia/Seoul",
        )

        def _make_sync_job(jname: str = job_name) -> None:
            """Wrap async run_scheduler_once for APScheduler (sync context)."""
            asyncio.run(run_scheduler_once(env_path=env_path, report_dir=report_dir))

        scheduler.add_job(_make_sync_job, trigger=trigger, id=job_name, name=job_name)
        print(f"[SCHEDULER] Registered {job_name!r} cron={cron_expr!r}")

    n = len(scheduler.get_jobs())
    if n == 0:
        raise RuntimeError("No valid cron jobs could be registered — check CRON_BATCH_* values.")
    print(f"[SCHEDULER] Starting APScheduler with {n} job(s). Timezone: Asia/Seoul.")
    scheduler.start()


async def main_async(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env_file(args.env_file)

    # APScheduler daemon mode (blocking; disabled by default)
    if args.apscheduler:
        run_with_apscheduler(env_path=args.env_file, report_dir=args.report_dir)
        return 0  # reached only when scheduler stops

    if args.plan_only or args.run_once is None:
        print(json.dumps(scheduler_plan(report_dir=args.report_dir), ensure_ascii=False, indent=2))
        return 0
    if args.max_iterations < 1:
        raise ValueError("--max-iterations must be >= 1")
    if args.sleep_seconds < 1 and args.max_iterations > 1:
        raise ValueError("--sleep-seconds must be >= 1")

    # Optional: filter to a single named job for manual PoC demo triggers
    job_filter: str | None = None if args.run_once == "__all__" else args.run_once

    latest: dict[str, Any] | None = None
    for index in range(args.max_iterations):
        if job_filter is not None:
            # Validate the job name exists before running
            available = {j.name for j in resolve_scheduler_jobs()}
            if job_filter not in available:
                print(
                    f"Unknown job {job_filter!r}. Available: {sorted(available)}",
                    file=sys.stderr,
                )
                return 3
        latest = await run_scheduler_once(
            env_path=args.env_file,
            report_dir=args.report_dir,
            job_filter=job_filter,
        )
        print(json.dumps(latest, ensure_ascii=False, default=str))
        if index + 1 < args.max_iterations:
            time.sleep(args.sleep_seconds)
    return 0 if latest and latest.get("ok") else 2


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
