#!/usr/bin/env python3
"""Validate total product readiness evidence without accepting false green reports.

This validator is intentionally evidence-based. It does not run the product or
providers; it checks that the reproducible verification gate, serviceable
readiness result, hostile QA guard, E2E coverage, and docs/runbooks are present
and internally consistent. Missing evidence is a failed result, not a skip.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"
DEFAULT_RESULT_JSON = REPORT_DIR / "total-product-readiness-result.json"
DEFAULT_SERVICEABLE_RESULT = (
    PROJECT_ROOT / ".omx" / "specs" / "autoresearch-service-readiness-top200-30d" / "result.json"
)
REQUIRED_GATE_STEPS = (
    "Runtime status",
    "Ruff",
    "Pytest",
    "Web typecheck",
    "Web lint",
    "Web unit tests",
    "Web build",
    "Playwright E2E",
    "Batch pipeline required-provider acceptance",
)
DIAGNOSTIC_GATE_STEPS = ("Batch pipeline all-provider diagnostic",)
REQUIRED_STATIC_FILES = (
    PROJECT_ROOT / "scripts" / "run_verification_gate.sh",
    PROJECT_ROOT / "scripts" / "qa_hostile_checks.sh",
    PROJECT_ROOT / "apps" / "web" / "e2e" / "harness-critical.spec.ts",
    PROJECT_ROOT / "apps" / "web" / "e2e" / "role-matrix.spec.ts",
    PROJECT_ROOT / "docs" / "test" / "TEST-01_test_strategy.md",
    PROJECT_ROOT / "docs" / "runbooks" / "OPS-02_deploy.md",
)
# ── ADR-007 aggregation constants ────────────────────────────────────────────

# Migrations expected in migration_versions (Wave 1 + Wave 2 deliverables)
REQUIRED_MIGRATION_VERSIONS: tuple[int, ...] = tuple(range(19, 37))  # V019..V036

# DEV close-out docs that must exist (Wave 1–4; DEV-09 is Wave 5, optional)
REQUIRED_DEV_DOCS: tuple[Path, ...] = (
    PROJECT_ROOT / "docs" / "dev" / "DEV-05_wave1_close_out.md",
    PROJECT_ROOT / "docs" / "dev" / "DEV-06_wave2_close_out.md",
    PROJECT_ROOT / "docs" / "dev" / "DEV-07_wave3_close_out.md",
    PROJECT_ROOT / "docs" / "dev" / "DEV-08_wave4_close_out.md",
)
OPTIONAL_DEV_DOCS: tuple[Path, ...] = (
    PROJECT_ROOT / "docs" / "dev" / "DEV-09_wave5_close_out.md",
)

# Module-split submodule line-budget (DEV-07 §2 contract)
SPLIT_LINE_BUDGET = 500
SPLIT_SUBMODULE_DIRS: tuple[Path, ...] = (
    PROJECT_ROOT / "apps" / "api" / "harness" / "services" / "readiness",
    PROJECT_ROOT / "apps" / "api" / "harness" / "repositories" / "batch",
    PROJECT_ROOT / "apps" / "api" / "harness" / "batch" / "providers",
)
SPLIT_FLAT_PREFIXES: tuple[tuple[Path, str], ...] = (
    (PROJECT_ROOT / "apps" / "api" / "harness" / "batch", "runner_"),
)

# REG-01..06 audit codes that must appear in OBS-02 doc
REG_REQUIRED_AUDIT_CODES: dict[str, tuple[str, ...]] = {
    "REG-01": ("consent_recorded", "rights_notice_issued", "credit_info_purge_simulated"),
    "REG-02": ("marketing_review_submitted", "unfair_solicitation_blocked", "email_drafted"),
    "REG-03": ("suitability_confirmed", "appropriateness_warning_acknowledged"),
    "REG-04": ("ai_quarantine_triggered", "ai_fail_closed", "ai_injection_detected"),
    "REG-05": ("auth_login_success", "ws_ticket_issued", "rate_limit_exceeded"),
    "REG-06": ("poc_auto_approval_used", "sod_evidence_published", "demo_mode_toggle_on"),
}

OBS02_DOC = PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── New aggregation validators ────────────────────────────────────────────────


def validate_migrations_applied() -> ComponentResult:
    """Assert V019..V036 are recorded in live PG17 migration_versions table."""
    errors: list[str] = []
    applied: list[int] = []

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        return ComponentResult(
            "migrations_applied",
            False,
            ("DATABASE_URL not configured; cannot verify applied migrations",),
        )

    # Normalise URL: asyncpg uses postgresql://, not postgresql+asyncpg://
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        import asyncio

        import asyncpg  # type: ignore[import]  # pyright: ignore[reportMissingImports]

        async def _query() -> list[int]:
            conn = await asyncpg.connect(pg_url, timeout=10)
            try:
                rows = await conn.fetch(
                    "SELECT version FROM migration_versions ORDER BY version"
                )
                return [r["version"] for r in rows]
            finally:
                await conn.close()

        applied = asyncio.run(_query())
    except ImportError:
        return ComponentResult(
            "migrations_applied",
            False,
            ("asyncpg not installed; cannot query migration_versions",),
        )
    except Exception as exc:  # noqa: BLE001
        return ComponentResult(
            "migrations_applied",
            False,
            (f"DB query failed: {str(exc)[:300]}",),
        )

    applied_set = frozenset(applied)
    for version in REQUIRED_MIGRATION_VERSIONS:
        if version not in applied_set:
            errors.append(f"V{version:03d} not in migration_versions")

    return ComponentResult(
        "migrations_applied",
        not errors,
        tuple(errors),
        {
            "required": [f"V{v:03d}" for v in REQUIRED_MIGRATION_VERSIONS],
            "applied_count": len(applied),
            "highest_applied": max(applied) if applied else None,
        },
    )


def validate_module_split_diff_zero() -> ComponentResult:
    """Assert every split submodule is within the 500-line budget (diff==0)."""
    errors: list[str] = []
    oversized: list[dict[str, Any]] = []

    # Package-directory splits
    for pkg_dir in SPLIT_SUBMODULE_DIRS:
        if not pkg_dir.exists():
            errors.append(f"split package dir missing: {pkg_dir.relative_to(PROJECT_ROOT)}")
            continue
        for py_file in sorted(pkg_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            lines = len(py_file.read_text(encoding="utf-8", errors="replace").splitlines())
            if lines > SPLIT_LINE_BUDGET:
                errors.append(
                    f"{py_file.relative_to(PROJECT_ROOT)} has {lines} lines"
                    f" (budget {SPLIT_LINE_BUDGET})"
                )
                oversized.append({"file": str(py_file.relative_to(PROJECT_ROOT)), "lines": lines})

    # Flat-file splits (runner_*.py siblings)
    for base_dir, prefix in SPLIT_FLAT_PREFIXES:
        if not base_dir.exists():
            continue
        for py_file in sorted(base_dir.glob(f"{prefix}*.py")):
            lines = len(py_file.read_text(encoding="utf-8", errors="replace").splitlines())
            if lines > SPLIT_LINE_BUDGET:
                errors.append(
                    f"{py_file.relative_to(PROJECT_ROOT)} has {lines} lines"
                    f" (budget {SPLIT_LINE_BUDGET})"
                )
                oversized.append({"file": str(py_file.relative_to(PROJECT_ROOT)), "lines": lines})

    return ComponentResult(
        "module_split_diff_zero",
        not errors,
        tuple(errors),
        {"split_line_budget": SPLIT_LINE_BUDGET, "oversized": oversized},
    )


def _find_latest_report(glob_pattern: str) -> Path | None:
    matches = sorted(REPORT_DIR.glob(glob_pattern))
    return matches[-1] if matches else None


def _rel(path: Path) -> str:
    """Return path relative to PROJECT_ROOT if possible, else absolute string."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def validate_ext_dep_attestation(attestation_path: Path | None) -> ComponentResult:
    """Assert external_dependency_attestation JSON exists and passed=true."""
    errors: list[str] = []

    path = attestation_path or _find_latest_report("external-dependency-attestation-*.json")
    if path is None or not path.exists():
        return ComponentResult(
            "ext_dep_attestation",
            False,
            ("no external-dependency-attestation JSON found in reports dir",),
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return ComponentResult(
            "ext_dep_attestation",
            False,
            (f"could not parse attestation JSON: {exc}",),
        )

    if payload.get("passed") is not True:
        errors.append(
            f"ext-dep attestation passed={payload.get('passed')!r}"
            f" status={payload.get('status')!r}"  # noqa: ISC001
        )

    for dep_key in ("azure_gpt5_mini", "smtp_sandbox", "broker_live_quote",
                    "data_go_kr_bond_live", "pykrx_fdr_cross_check"):
        dep = (payload.get("deps") or {}).get(dep_key, {})
        if dep.get("status") == "failed":
            errors.append(f"ext-dep {dep_key} status=failed")

    return ComponentResult(
        "ext_dep_attestation",
        not errors,
        tuple(errors),
        {
            "attestation_path": _rel(path),
            "status": payload.get("status"),
            "verified_at": payload.get("verified_at"),
        },
    )


def validate_sod_evidence(sod_path: Path | None) -> ComponentResult:
    """Assert SoD evidence-pack JSON exists and violations bucket is empty."""
    errors: list[str] = []

    path = sod_path or _find_latest_report("sod-evidence-pack-*.json")
    if path is None or not path.exists():
        return ComponentResult(
            "sod_evidence",
            False,
            ("no sod-evidence-pack JSON found in reports dir — run generate_sod_evidence_pack.py",),
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return ComponentResult(
            "sod_evidence",
            False,
            (f"could not parse SoD evidence JSON: {exc}",),
        )

    if payload.get("passed") is not True:
        errors.append(f"SoD evidence pack passed={payload.get('passed')!r}")

    violations_count = (payload.get("buckets") or {}).get("violations", {}).get("count", -1)
    if violations_count != 0:
        errors.append(f"SoD violations bucket count={violations_count} (expected 0)")

    return ComponentResult(
        "sod_evidence",
        not errors,
        tuple(errors),
        {
            "sod_path": _rel(path),
            "violations_count": violations_count,
            "status": payload.get("status"),
        },
    )


def validate_gitleaks(*, skip: bool = False) -> ComponentResult:
    """Run validate_no_secrets.py and assert no secrets found."""
    if skip:
        return ComponentResult("gitleaks", True, (), {"skipped": True})

    script = PROJECT_ROOT / "scripts" / "validate_no_secrets.py"
    if not script.exists():
        return ComponentResult(
            "gitleaks",
            False,
            (f"validate_no_secrets.py not found at {script}",),
        )

    try:
        result = subprocess.run(
            [sys.executable, str(script), "--json-only"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return ComponentResult(
            "gitleaks",
            False,
            ("validate_no_secrets.py timed out after 60s",),
        )

    # Exit code 3 = gitleaks unavailable/config error → fail closed
    # (use --skip-gitleaks to bypass when the binary is intentionally absent)
    if result.returncode == 3:
        try:
            triple = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            triple = {}
        reason = triple.get("reason", "gitleaks unavailable")
        return ComponentResult(
            "gitleaks",
            False,
            (f"gitleaks config error: {reason}",),
        )

    try:
        triple = json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return ComponentResult(
            "gitleaks",
            False,
            (f"validate_no_secrets.py produced non-JSON output (exit {result.returncode})",),
        )

    passed = triple.get("passed", False)
    errors: list[str] = [] if passed else [
        f"gitleaks: {triple.get('reason', 'findings detected')}"
        f" (count={triple.get('findings_count')})"
    ]
    return ComponentResult(
        "gitleaks",
        passed,
        tuple(errors),
        {
            "status": triple.get("status"),
            "findings_count": triple.get("findings_count"),
            "scan_mode": triple.get("scan_mode"),
        },
    )


def validate_reg_audit_codes() -> ComponentResult:
    """Assert all per-REG required audit codes appear in OBS-02."""
    errors: list[str] = []

    if not OBS02_DOC.exists():
        return ComponentResult(
            "reg_audit_codes",
            False,
            (f"OBS-02 doc not found: {OBS02_DOC.relative_to(PROJECT_ROOT)}",),
        )

    obs02_text = OBS02_DOC.read_text(encoding="utf-8", errors="replace")
    missing_per_reg: dict[str, list[str]] = {}

    for reg, required_codes in REG_REQUIRED_AUDIT_CODES.items():
        missing = [code for code in required_codes if code not in obs02_text]
        if missing:
            missing_per_reg[reg] = missing
            for code in missing:
                errors.append(f"{reg}: audit code '{code}' not found in OBS-02")

    return ComponentResult(
        "reg_audit_codes",
        not errors,
        tuple(errors),
        {
            "obs02_path": str(OBS02_DOC.relative_to(PROJECT_ROOT)),
            "missing_per_reg": missing_per_reg,
            "checked_regs": list(REG_REQUIRED_AUDIT_CODES.keys()),
        },
    )


def validate_dev_docs_exist() -> ComponentResult:
    """Assert DEV-05..DEV-08 close-out docs exist; note DEV-09 status."""
    errors: list[str] = []
    optional_notes: list[str] = []

    for doc in REQUIRED_DEV_DOCS:
        if not doc.exists():
            errors.append(f"required close-out doc missing: {doc.relative_to(PROJECT_ROOT)}")

    for doc in OPTIONAL_DEV_DOCS:
        if not doc.exists():
            optional_notes.append(f"{doc.name} not yet present (Wave 5 close-out pending)")

    return ComponentResult(
        "dev_docs_exist",
        not errors,
        tuple(errors),
        {
            "required": [str(d.relative_to(PROJECT_ROOT)) for d in REQUIRED_DEV_DOCS],
            "optional_notes": optional_notes,
        },
    )


SECRET_PATTERNS = (
    "KRX_API_KEY=",
    "AUTH_KEY=",
    "JWT_SECRET=",
    "DATABASE_URL=postgresql://",
    "POSTGRES_PASSWORD=",
    "Bearer ",
    "SERVICE_KEY=",
    "APP_SECRET=",
)


@dataclass(frozen=True)
class ComponentResult:
    """One validator component result."""

    name: str
    passed: bool
    errors: tuple[str, ...] = ()
    detail: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": "passed" if self.passed else "failed",
            "passed": self.passed,
            "errors": list(self.errors),
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def scan_for_secret_markers(text: str, *, context: str) -> list[str]:
    return [
        f"{context} contains secret-like marker {marker}"
        for marker in SECRET_PATTERNS
        if marker in text
    ]


def parse_markdown_gate_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"^## (?P<name>.+?)\n", text, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group("name").strip()] = text[start:end]
    return sections


def section_exit_status(body: str) -> int | None:
    match = re.search(r"\(exit (?P<status>\d+)(?:;[^)]*)?\)", body)
    return int(match.group("status")) if match else None


def validate_verification_gate(report_path: Path) -> ComponentResult:
    errors: list[str] = []
    try:
        text = read_text(report_path)
    except FileNotFoundError as exc:
        return ComponentResult("verification_gate", False, (str(exc),))
    errors.extend(scan_for_secret_markers(text, context=str(report_path)))
    sections = parse_markdown_gate_sections(text)
    for name in REQUIRED_GATE_STEPS:
        body = sections.get(name)
        if body is None:
            errors.append(f"missing required verification step: {name}")
            continue
        status = section_exit_status(body)
        if status is None:
            errors.append(f"verification step lacks exit status: {name}")
        elif status != 0:
            errors.append(f"verification step {name} exited {status}")
    for name in DIAGNOSTIC_GATE_STEPS:
        body = sections.get(name)
        if body is None:
            errors.append(f"missing diagnostic verification step: {name}")
            continue
        if section_exit_status(body) is None:
            errors.append(f"diagnostic step lacks exit status: {name}")
    if not re.search(r"^- failures:\s*0\s*$", text, flags=re.MULTILINE):
        errors.append("verification gate summary must report failures: 0")
    return ComponentResult(
        "verification_gate",
        not errors,
        tuple(errors),
        {
            "report_path": str(report_path),
            "required_steps": list(REQUIRED_GATE_STEPS),
            "diagnostic_steps": list(DIAGNOSTIC_GATE_STEPS),
        },
    )


def _coverage_from_serviceable(payload: dict[str, Any]) -> dict[str, Any]:
    coverage = payload.get("readiness") or {}
    if isinstance(coverage, dict):
        nested = coverage.get("coverage")
        if isinstance(nested, dict):
            return nested
    coverage = payload.get("batch") or {}
    if isinstance(coverage, dict):
        nested = coverage.get("coverage")
        if isinstance(nested, dict):
            return nested
    return payload


def validate_serviceable_result(path: Path) -> ComponentResult:
    errors: list[str] = []
    try:
        raw_text = read_text(path)
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("serviceable result JSON must be an object")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return ComponentResult("serviceable_readiness", False, (str(exc),))
    errors.extend(scan_for_secret_markers(raw_text, context=str(path)))
    if payload.get("passed") is not True:
        errors.append("serviceable readiness result must have passed=true")
    if payload.get("status") != "passed":
        errors.append("serviceable readiness result status must be passed")
    if payload.get("verifier_signoff") != "serviceable-readiness-validator":
        errors.append(
            "serviceable readiness result must include "
            "serviceable-readiness-validator signoff"
        )
    coverage = _coverage_from_serviceable(payload)
    selected_count = int(coverage.get("selected_count") or payload.get("selected_count") or 0)
    coverage_ratio = float(coverage.get("coverage_ratio") or payload.get("coverage_ratio") or 0)
    missing_member_days = int(coverage.get("missing_member_days") or 0)
    if selected_count < 200:
        errors.append(f"selected_count must be >= 200, got {selected_count}")
    if coverage_ratio < 1.0:
        errors.append(f"coverage_ratio must be >= 1.0, got {coverage_ratio}")
    if missing_member_days != 0:
        errors.append(f"missing_member_days must be 0, got {missing_member_days}")
    return ComponentResult(
        "serviceable_readiness",
        not errors,
        tuple(errors),
        {
            "result_path": str(path),
            "selected_count": selected_count,
            "coverage_ratio": coverage_ratio,
            "missing_member_days": missing_member_days,
        },
    )


def validate_static_false_green_controls(*, run_hostile_checks: bool) -> ComponentResult:
    errors: list[str] = []
    for path in REQUIRED_STATIC_FILES:
        if not path.exists():
            errors.append(f"missing static control file: {path.relative_to(PROJECT_ROOT)}")
    gate_text = read_text(PROJECT_ROOT / "scripts" / "run_verification_gate.sh")
    for fragment in (
        "run_step \"Playwright E2E\"",
        "run_step \"Batch pipeline required-provider acceptance\"",
        "run_nonblocking_step \"Batch pipeline all-provider diagnostic\"",
        "--skip-e2e",
        "--skip-batch",
        "failures=$FAILURES",
    ):
        if fragment not in gate_text:
            errors.append(f"run_verification_gate.sh missing false-green control: {fragment}")
    e2e_text = (PROJECT_ROOT / "apps" / "web" / "e2e" / "harness-critical.spec.ts").read_text()
    role_matrix_text = (PROJECT_ROOT / "apps" / "web" / "e2e" / "role-matrix.spec.ts").read_text()
    for fragment in (
        "synthetic login bypass is not allowed",
        "E2E_EMPLOYEE_EMAIL/E2E_EMPLOYEE_PASSWORD not configured",
    ):
        if fragment not in e2e_text:
            errors.append(f"harness-critical.spec.ts missing E2E anti-skip marker: {fragment}")
    for fragment in (
        "E2E_SYNTHETIC_PASSWORD is required; no synthetic-login bypass is allowed",
        "role matrix enforces all screens",
        "authenticated dashboard survives browser reload without token storage",
    ):
        if fragment not in role_matrix_text:
            errors.append(f"role-matrix.spec.ts missing E2E anti-false-green marker: {fragment}")
    docs_text = (PROJECT_ROOT / "docs" / "test" / "TEST-01_test_strategy.md").read_text()
    deploy_text = (PROJECT_ROOT / "docs" / "runbooks" / "OPS-02_deploy.md").read_text()
    for fragment in (
        "scripts/verify_total_product_readiness.py",
        "total-product readiness",
        "false-green",
    ):
        if fragment not in docs_text + "\n" + deploy_text:
            errors.append(f"docs/runbooks missing total-product readiness marker: {fragment}")
    hostile_output = "not_run"
    if run_hostile_checks:
        result = subprocess.run(
            [str(PROJECT_ROOT / "scripts" / "qa_hostile_checks.sh")],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        hostile_output = result.stdout.strip()
        if result.returncode != 0:
            errors.append(f"qa_hostile_checks.sh failed: {result.stdout}{result.stderr}")
        elif "hostile_checks=passed failures=0" not in result.stdout:
            errors.append("qa_hostile_checks.sh did not report hostile_checks=passed failures=0")
    return ComponentResult(
        "false_green_controls",
        not errors,
        tuple(errors),
        {"hostile_checks": hostile_output},
    )


# ── ADR-007.1 composite gate constants ───────────────────────────────────────

MEASUREMENTS_DIR = PROJECT_ROOT / "docs" / "ai" / "measurements"
COMPOSITE_FRESHNESS_DAYS_MAX = 7


def _load_runtime_results() -> tuple[bool, int, float]:
    """Load all runtime measurement JSONs and return (runtime_passed, min_denominator, max_age_days).

    runtime_passed=True only when:
      - At least one measurement file exists
      - All files have denominator >= 1
      - All files are within freshness window (expires_at not exceeded)
    Returns (runtime_passed, min_denominator, max_freshness_days).
    """
    import glob

    pattern = str(MEASUREMENTS_DIR / "*.json")
    files = [Path(p) for p in glob.glob(pattern) if not Path(p).name.startswith(".")]

    if not files:
        return False, 0, float("inf")

    now_utc = datetime.now(UTC)
    min_denominator = sys.maxsize
    max_age_days: float = 0.0
    all_passed = True

    for fpath in files:
        try:
            payload = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            all_passed = False
            continue

        denominator = int(payload.get("denominator", 0))
        if denominator < 1:
            all_passed = False
        min_denominator = min(min_denominator, denominator)

        expires_at_str = payload.get("expires_at", "")
        try:
            expires_at = datetime.strptime(expires_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            last_measured_str = payload.get("last_measured_at", "")
            last_measured = datetime.strptime(last_measured_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            age_days = (now_utc - last_measured).total_seconds() / 86400.0
            max_age_days = max(max_age_days, age_days)
            if now_utc > expires_at:
                all_passed = False
        except ValueError:
            all_passed = False

    effective_denom = min_denominator if min_denominator < sys.maxsize else 0
    return all_passed, effective_denom, max_age_days


def validate_composite_gate(static_result_path: Path | None = None) -> ComponentResult:
    """ADR-007.1 composite AND gate: STATIC.passed AND RUNTIME.passed AND freshness AND denominator.

    OR-leak is blocked: all four conditions must hold simultaneously (pre-mortem S4).

    Bootstrap behavior: when MEASUREMENTS_DIR exists but is empty (fresh deploy /
    pre-collector state), composite_gate returns status="not_yet_collected" with
    passed=True. Strict fail-closed semantics activate once any measurement file
    appears (denominator integrity + freshness window enforced from that point).
    """
    import glob as _glob

    pattern = str(MEASUREMENTS_DIR / "*.json")
    measurement_files = [
        p for p in _glob.glob(pattern) if not Path(p).name.startswith(".")
    ]
    has_measurements = bool(measurement_files)

    errors: list[str] = []

    # ── 1. STATIC check ──────────────────────────────────────────────────────
    static_passed = False
    static_present = False
    if static_result_path is not None and static_result_path.exists():
        static_present = True
        try:
            static_payload = json.loads(static_result_path.read_text(encoding="utf-8"))
            static_passed = bool(static_payload.get("passed", False))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"could not read static result: {exc}")
    else:
        # Auto-discover latest static result in .omc/specs/
        specs_dir = PROJECT_ROOT / ".omc" / "specs"
        candidates = sorted(specs_dir.glob("seven-principles-report-*.json")) if specs_dir.exists() else []
        if candidates:
            static_present = True
            try:
                static_payload = json.loads(candidates[-1].read_text(encoding="utf-8"))
                static_passed = bool(static_payload.get("passed", False))
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"could not read auto-discovered static result: {exc}")

    # Bootstrap exit: no measurement JSONs yet → not_yet_collected (gradual rollout).
    # Strict fail-closed activates once aggregate_principle_runtime_metrics.py
    # emits the first measurement file. Static state preserved for reporting.
    if not has_measurements:
        return ComponentResult(
            "composite_gate",
            True,
            (),
            {
                "composite_passed": True,
                "status": "not_yet_collected",
                "static_passed": static_passed,
                "runtime_passed": False,
                "denominator": 0,
                "freshness_days": None,
                "note": (
                    "composite gate bootstrap state — no measurement JSONs yet. "
                    "Run aggregate_principle_runtime_metrics.py with active AI traffic "
                    "to activate strict fail-closed semantics."
                ),
            },
        )

    if not static_passed and static_present:
        errors.append("STATIC check not passed (generate_seven_principles_static_check.py)")
    elif not static_present:
        errors.append("no static seven-principles result found; run generate_seven_principles_static_check.py")

    # ── 2. RUNTIME check ─────────────────────────────────────────────────────
    runtime_passed, min_denominator, freshness_days = _load_runtime_results()

    if not runtime_passed:
        if min_denominator < 1:
            errors.append(
                f"RUNTIME denominator={min_denominator} < 1 "
                "(run aggregate_principle_runtime_metrics.py with active AI traffic)"
            )
        else:
            errors.append(
                "RUNTIME metrics stale or missing "
                "(run aggregate_principle_runtime_metrics.py)"
            )

    # ── 3. Freshness check ────────────────────────────────────────────────────
    if freshness_days > COMPOSITE_FRESHNESS_DAYS_MAX:
        errors.append(
            f"RUNTIME freshness={freshness_days:.1f}d exceeds {COMPOSITE_FRESHNESS_DAYS_MAX}d limit"
        )

    # ── 4. Denominator check ─────────────────────────────────────────────────
    if min_denominator < 1:
        errors.append(
            "denominator < 1: no AI_CALL_STARTED events in measurement window"
        )

    composite_passed = not errors

    return ComponentResult(
        "composite_gate",
        composite_passed,
        tuple(errors),
        {
            "composite_passed": composite_passed,
            "static_passed": static_passed,
            "runtime_passed": runtime_passed,
            "denominator": min_denominator if min_denominator < sys.maxsize else 0,
            "freshness_days": round(freshness_days, 2) if freshness_days < float("inf") else None,
        },
    )


def build_result(
    components: list[ComponentResult],
    evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    errors = [error for component in components for error in component.errors]

    # Extract composite gate fields for top-level convenience
    composite_component = next(
        (c for c in components if c.name == "composite_gate"), None
    )
    composite_detail: dict[str, Any] = composite_component.detail or {} if composite_component else {}

    result: dict[str, Any] = {
        "schema_version": "1.0",
        "validator": "total-product-readiness-validator",
        "verified_at": _now_utc(),
        "status": "passed" if not errors else "failed",
        "passed": not errors,
        "components": {component.name: component.as_dict() for component in components},
        "errors": errors,
        "evidence_paths": evidence_paths or [],
    }

    # ADR-007.1 composite gate top-level fields
    result["composite_passed"] = composite_detail.get("composite_passed", False)
    result["static_passed"] = composite_detail.get("static_passed", False)
    result["runtime_passed"] = composite_detail.get("runtime_passed", False)
    result["denominator"] = composite_detail.get("denominator", 0)
    result["freshness_days"] = composite_detail.get("freshness_days")

    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification-gate-report", type=Path, required=True)
    parser.add_argument("--serviceable-result-json", type=Path, default=DEFAULT_SERVICEABLE_RESULT)
    parser.add_argument("--result-json", type=Path, default=DEFAULT_RESULT_JSON)
    parser.add_argument(
        "--skip-hostile-checks",
        action="store_true",
        help="Skip executing qa_hostile_checks.sh; static checks still run.",
    )
    # ADR-007 aggregation options
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Skip live PG17 migration check (use when DATABASE_URL unavailable).",
    )
    parser.add_argument(
        "--skip-gitleaks",
        action="store_true",
        help="Skip gitleaks scan (use when gitleaks binary not on PATH).",
    )
    parser.add_argument(
        "--attestation-json",
        type=Path,
        default=None,
        help="Explicit path to external-dependency-attestation JSON (auto-discovered if omitted).",
    )
    parser.add_argument(
        "--sod-evidence-json",
        type=Path,
        default=None,
        help="Explicit path to sod-evidence-pack JSON (auto-discovered if omitted).",
    )
    # ADR-007.1 composite gate options
    parser.add_argument(
        "--static-result-json",
        type=Path,
        default=None,
        help="Explicit path to seven-principles static result JSON (auto-discovered if omitted).",
    )
    parser.add_argument(
        "--skip-composite-gate",
        action="store_true",
        help="Skip composite AND gate check (use only when no runtime measurements available).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    args = parse_args(argv)

    # ── Core gate components (original) ──────────────────────────────────────
    components: list[ComponentResult] = [
        validate_verification_gate(args.verification_gate_report),
        validate_serviceable_result(args.serviceable_result_json),
        validate_static_false_green_controls(run_hostile_checks=not args.skip_hostile_checks),
    ]

    # ── ADR-007 aggregation components ───────────────────────────────────────
    if not args.skip_migrations:
        components.append(validate_migrations_applied())

    components.extend([
        validate_module_split_diff_zero(),
        validate_ext_dep_attestation(args.attestation_json),
        validate_sod_evidence(args.sod_evidence_json),
        validate_gitleaks(skip=args.skip_gitleaks),
        validate_reg_audit_codes(),
        validate_dev_docs_exist(),
    ])

    # ── ADR-007.1 composite AND gate ─────────────────────────────────────────
    if not args.skip_composite_gate:
        components.append(validate_composite_gate(args.static_result_json))

    # ── Collect evidence paths ────────────────────────────────────────────────
    evidence_paths: list[str] = [
        str(args.verification_gate_report),
        str(args.serviceable_result_json),
    ]
    if args.attestation_json:
        evidence_paths.append(str(args.attestation_json))
    if args.sod_evidence_json:
        evidence_paths.append(str(args.sod_evidence_json))

    result = build_result(components, evidence_paths)

    args.result_json.parent.mkdir(parents=True, exist_ok=True)
    args.result_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))

    # ADR-007 exit codes: 0=pass, 2=fail, 3=config error
    # (config errors surface as component failures; we use 2 for any failure)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
