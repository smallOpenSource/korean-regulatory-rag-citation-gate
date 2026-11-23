#!/usr/bin/env python3
"""Validate Stage 0.5 architecture contract documentation scaffolds.

This gate is intentionally static and read-only. It checks docs/manifests so a
future implementation lane does not accidentally promote WebSocket, dependency,
large-module, or operations contracts without synchronized docs. Email is
validated as an implemented provider-gated backend contract.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx"}
IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".omx",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "node_modules",
}
LARGE_MODULE_THRESHOLD = 500

REQUIRED_DOC_TOKENS = {
    "docs/architecture/ARCH-01_stage_0_5_contract_inventory.md": [
        "Stage 0.5",
        "WebSocket delivery",
        "Email draft/send",
        "Dependency changes",
        "Large modules",
        "Operations status",
    ],
    "docs/architecture/ADR-001_websocket_delivery_contract.md": [
        "backlog/not-current-contract",
        "event_id",
        "tenant_scope",
        "row_scope",
        "access token",
        "Refresh cookies",
    ],
    "docs/architecture/ADR-002_email_authority_and_schema_contract.md": [
        "implemented",
        "PB/WM",
        "ADMIN",
        "APPROVED",
        "email_draft_send",
        "email_sent_via_sandbox",
        "SQL_ID",
    ],
    "docs/architecture/ADR-003_dependency_change_gate.md": [
        "Current Dependency Manifest Allowlist",
        "asyncpg",
        "@tanstack/react-query",
        "Forbidden without",
    ],
    "docs/dev/DEV-02_large_module_containment.md": [
        "Current Containment Register",
        "500 lines",
        "apps/api/harness/batch/runner.py",
    ],
    "docs/runbooks/OPS-04_operations_status.md": [
        "scripts/status.sh --deep --no-fail",
        "/batch/status",
        "/data/readiness",
        "backlog/not-current-contract",
        "<redacted>",
    ],
    "docs/api/API-02_websocket.md": [
        "backlog/not-current-contract",
        "event_id",
        "row_scope",
        "tenant_scope",
    ],
    "docs/integration/INT-03_email.md": [
        "Current Status",
        "Authority Model",
        "Current Draft Schema",
        "email_draft_send",
        "email_sent_via_sandbox",
    ],
}


@dataclass
class ValidationResult:
    checks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def check(self, name: str) -> None:
        self.checks.append(name)

    def error(self, message: str) -> None:
        self.errors.append(message)


def read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def validate_required_docs(result: ValidationResult) -> None:
    result.check("required_docs")
    for relative_path, tokens in REQUIRED_DOC_TOKENS.items():
        path = PROJECT_ROOT / relative_path
        if not path.exists():
            result.error(f"missing required architecture doc: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                result.error(f"{relative_path} missing required token: {token}")


def validate_contract_scope(result: ValidationResult) -> None:
    result.check("contract_scope")
    api_contract = read_text("docs/api/API-01_contracts.yaml")
    api_ws = read_text("docs/api/API-02_websocket.md")
    email = read_text("docs/integration/INT-03_email.md")
    async_spec = read_text("docs/async/ASYNC-01_realtime_spec.md")
    ops = read_text("docs/runbooks/OPS-04_operations_status.md")

    for token in ("email draft/send", "WebSocket push", "backlog/not-current-contract"):
        if token not in api_contract:
            result.error(f"API-01 contract description lost scope token: {token}")

    for path_name, text in {
        "API-02": api_ws,
        "ASYNC-01": async_spec,
        "OPS-04": ops,
    }.items():
        if "backlog/not-current-contract" not in text:
            result.error(f"{path_name} must label non-current push contract status")

    for token in ("POST /email-drafts", "POST /email-drafts/{draft_id}/send"):
        if token not in email:
            result.error(f"INT-03 missing implemented email route token: {token}")

    if "Refresh cookies" not in api_ws or "not WebSocket authorization" not in api_ws:
        result.error("API-02 must keep refresh cookies out of WebSocket authorization")
    if "ADMIN system authority is not PB/WM customer communication authority" not in email:
        result.error("INT-03 must separate ADMIN system authority from PB/WM send authority")
    if "scripts/status.sh --deep --no-fail" not in ops:
        result.error("OPS-04 must document the local status evidence command")


def parse_dependency_allowlist() -> dict[str, set[str]]:
    text = read_text("docs/architecture/ADR-003_dependency_change_gate.md")
    allowed: dict[str, set[str]] = {"python": set(), "js-runtime": set(), "js-dev": set()}
    row_re = re.compile(r"^\|\s*(python|js-runtime|js-dev)\s*\|\s*([^|`]+?)\s*\|")
    for line in text.splitlines():
        match = row_re.match(line)
        if match:
            allowed[match.group(1)].add(match.group(2).strip())
    return allowed


def python_dependency_names() -> set[str]:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names: set[str] = set()
    for dependency in pyproject.get("project", {}).get("dependencies", []):
        name = re.split(r"[<>=!~;\s\[]", dependency, maxsplit=1)[0]
        names.add(name)
    return names


def package_json_dependency_names(section: str) -> set[str]:
    package_json = json.loads((PROJECT_ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    return set(package_json.get(section, {}))


def validate_dependency_allowlist(result: ValidationResult) -> None:
    result.check("dependency_allowlist")
    allowed = parse_dependency_allowlist()
    expected = {
        "python": python_dependency_names(),
        "js-runtime": package_json_dependency_names("dependencies"),
        "js-dev": package_json_dependency_names("devDependencies"),
    }
    result.details["dependency_counts"] = {key: len(value) for key, value in expected.items()}

    for ecosystem, declared in expected.items():
        missing = sorted(declared - allowed.get(ecosystem, set()))
        stale = sorted(allowed.get(ecosystem, set()) - declared)
        if missing:
            result.error(f"dependency ADR missing {ecosystem} package(s): {', '.join(missing)}")
        if stale:
            result.error(f"dependency ADR has stale {ecosystem} package(s): {', '.join(stale)}")


def source_files() -> list[Path]:
    paths: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if set(path.relative_to(PROJECT_ROOT).parts) & IGNORED_PARTS:
            continue
        paths.append(path)
    return paths


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def validate_large_module_register(result: ValidationResult) -> None:
    result.check("large_module_register")
    containment = read_text("docs/dev/DEV-02_large_module_containment.md")
    oversized = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in source_files()
        if line_count(path) > LARGE_MODULE_THRESHOLD
    ]
    result.details["oversized_files"] = oversized
    for relative_path in oversized:
        if f"`{relative_path}`" not in containment:
            result.error(
                f"large module over {LARGE_MODULE_THRESHOLD} lines missing containment entry: "
                f"{relative_path}"
            )


def validate_ops_doc_sync(result: ValidationResult) -> None:
    result.check("ops_doc_sync")
    ops01 = read_text("docs/runbooks/OPS-01_server_setup.md")
    ops02 = read_text("docs/runbooks/OPS-02_deploy.md")
    ops03 = read_text("docs/runbooks/OPS-03_troubleshooting.md")
    obs01 = read_text("docs/observability/OBS-01_logging_spec.md")
    test_strategy = read_text("docs/test/TEST-01_test_strategy.md")

    required_pairs = {
        "OPS-01": (ops01, "--no-fail"),
        "OPS-02": (ops02, "OPS-04"),
        "OPS-03": (ops03, "status=blocked failures=N no_fail=1"),
        "OBS-01": (obs01, "scripts/status.sh --deep --no-fail"),
        "TEST-01": (test_strategy, "validate_architecture_contracts.py"),
    }
    for name, (text, token) in required_pairs.items():
        if token not in text:
            result.error(f"{name} missing operations/docs sync token: {token}")


def run_validation() -> ValidationResult:
    result = ValidationResult()
    validate_required_docs(result)
    validate_contract_scope(result)
    validate_dependency_allowlist(result)
    validate_large_module_register(result)
    validate_ops_doc_sync(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    args = parser.parse_args()

    result = run_validation()
    payload = {
        "status": "passed" if result.ok else "failed",
        "passed": result.ok,
        "checks": result.checks,
        "errors": result.errors,
        "details": result.details,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"architecture_contracts={payload['status']} checks={len(result.checks)}")
        for error in result.errors:
            print(f"error={error}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
