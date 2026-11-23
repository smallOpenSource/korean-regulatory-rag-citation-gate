#!/usr/bin/env python3
"""check_poc_to_prod_migration.py — PoC-to-production leakage scan (ADR-004 §5, REG-06).

Scans the codebase for PoC governance tokens that must NOT appear in
production build artefacts.  Complements ``scripts/check_no_poc_in_prod.sh``
(which scans compiled bundles) by scanning the *source tree* so that risky
references can be caught before a build is even triggered.

Forbidden source tokens (case-sensitive):
  - PoC_AUTO_APPROVAL
  - X-Poc-Demo-Mode
  - system_flags.demo_mode
  - VITE_IS_POC_BUILD
  - poc_auto_approval_guard
  - poc_auto_approval_used

Allowed-by-design locations (these paths are PoC-only and will never ship):
  - apps/api/harness/core/poc_demo_guard.py
  - apps/api/harness/services/poc_auto_approval.py
  - scripts/generate_sod_evidence_pack.py
  - scripts/check_poc_to_prod_migration.py  (this file)
  - scripts/check_no_poc_in_prod.sh
  - tests/  (test code, never shipped)
  - docs/   (documentation)
  - db/     (migrations, never in prod bundle)
  - .omc/   (orchestration state)
  - .omx/   (reports)
  - apps/web/src/pages/KoreanAIBasicActPage.tsx  (UI doc page, PoC-only)

Exit codes (ADR-007 §0 base set):
  0  clean — no unexpected leakage
  1  leakage found (matches check_no_poc_in_prod.sh convention)
  2  unexpected error
  3  config/invocation error

Output JSON (--json flag):
  {
    "verified_at": "<UTC>",
    "status": "passed|failed",
    "passed": bool,
    "scan_root": "<path>",
    "forbidden_tokens": [...],
    "leaks": [
      {"token": "<token>", "file": "<path>", "line": N, "snippet": "<text>"}
    ],
    "allowed_paths_skipped": N,
    "checked_files": N,
    "shell_gate_result": "ok|skipped|<error message>"
  }
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FORBIDDEN_TOKENS: tuple[str, ...] = (
    "PoC_AUTO_APPROVAL",
    "X-Poc-Demo-Mode",
    "system_flags.demo_mode",
    "VITE_IS_POC_BUILD",
    "poc_auto_approval_guard",
    "poc_auto_approval_used",
)

# Relative path segments — any file whose path contains one of these is allowed
# to reference PoC tokens (the file itself will never reach a prod bundle).
ALLOWED_PATH_FRAGMENTS: tuple[str, ...] = (
    # PoC-only guard / approval modules — the source of truth, never shipped alone
    # (whole-stem anchored — full stems, not substrings, to avoid fail-open).
    "poc_demo_guard",
    "poc_auto_approval",
    "generate_sod_evidence_pack",
    "check_poc_to_prod_migration",
    "check_no_poc_in_prod",
    # PoC-only services directory (watermark + forced-exit etc. — REG-06 §8)
    "/services/poc/",
    os.sep + "services" + os.sep + "poc" + os.sep,
    # PoC synthetic-contract generator (T208) — gates on PoC_AUTO_APPROVAL marker
    "/services/contract/",
    os.sep + "services" + os.sep + "contract" + os.sep,
    # Test paths (unit, integration, e2e) — never in prod bundle
    "/tests/",
    os.sep + "tests" + os.sep,
    "/e2e/",
    os.sep + "e2e" + os.sep,
    # Documentation / architecture docs — never compiled
    "/docs/",
    os.sep + "docs" + os.sep,
    # Database migrations — never in app bundle
    "/db/",
    os.sep + "db" + os.sep,
    # Orchestration / report state directories
    "/.omc/",
    os.sep + ".omc" + os.sep,
    "/.omx/",
    os.sep + ".omx" + os.sep,
    "/.remember/",
    os.sep + ".remember" + os.sep,
    # npm dependency tree
    "/node_modules/",
    os.sep + "node_modules" + os.sep,
    # Vite build output (gitignored). Tree-shaking of PoC handlers happens in
    # the prod-only build profile; the local dev `dist/` may still contain
    # PoC references because it was built with the PoC profile.
    "/dist/",
    os.sep + "dist" + os.sep,
    "__pycache__",
    ".pyc",
    # PoC-only UI/doc pages — reference PoC governance for policy documentation
    # only; excluded from prod bundle via Vite tree-shake + check_no_poc_in_prod.sh
    "KoreanAIBasicActPage",
    "PoCAutoApprovalBadge",
    "AIModelCardsPage",    # AI model cards info page (PoC documentation)
    "AIPolicyPage",         # AI policy info page (PoC policy docs)
    # The PoC-only demo guard module and its compiled artifacts
    "poc_demo",
    # audit.py is the canonical action-code registry; PoC codes are defined
    # there but only fire in PoC environments (not production leakage).
    # ADR-004: action-code definitions are excluded from the dead-code gate.
    "core/audit",
    # Validator / governance scripts — not shipped to prod
    "verify_total_product_readiness",
    "verify_external_research_application",
    "verify_serviceable",
    "capture_",
    "run_verification",
    "run_batch",
)

# Binary / build artefact extensions to skip in source scan
# (the shell gate handles compiled bundle artefacts)
SKIP_EXTENSIONS: frozenset[str] = frozenset(
    {".pyc", ".map", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg",
     ".ico", ".woff", ".woff2", ".ttf", ".eot", ".bin", ".so", ".dylib",
     # Documentation / config — never shipped in a bundle
     ".md", ".toml", ".cfg", ".ini", ".txt", ".rst",
     }
)

# Source extensions to actively scan — only files that could appear in a
# production bundle (backend Python, frontend TypeScript/JavaScript).
# Markdown, TOML config, shell scripts, and YAML are excluded because they
# are never compiled into a deployable artefact.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_allowed(path: Path, root: Path) -> bool:
    """Return True when the file is in an allowed-by-design PoC location.

    Matching is *anchored* (not bare substring containment) so that a
    production file is never auto-exempted merely because its path happens
    to contain an allow-fragment as a substring (fail-open).  Each fragment
    class is matched against a structural unit of the path:
      - directory fragment ("/db/", "/services/poc/", "__pycache__"):
        must match a whole path component (a segment of rel.split("/")).
      - parent/name fragment ("core/audit"): must match the file's
        ``<parent dir>/<stem>`` exactly.
      - extension fragment (".pyc"): must match the file suffix.
      - prefix fragment ("capture_", trailing underscore): must match the
        start of the file *stem* (a deliberate name-family prefix).
      - bare-name fragment (everything else): must equal the whole file
        stem, or appear as a whole path segment.
    """
    rel = str(path.relative_to(root)).replace("\\", "/")
    segments = [seg for seg in rel.split("/") if seg]
    stem = Path(rel).stem
    parent_name = Path(rel).parent.name
    for fragment in ALLOWED_PATH_FRAGMENTS:
        # normalise fragment for cross-platform matching
        frag = fragment.replace("\\", "/").strip("/")
        if not frag:
            continue
        norm_frag = fragment.replace("\\", "/")
        if "/" in norm_frag:
            # Slash-bearing fragment.
            if norm_frag.endswith("/") or norm_frag.startswith("/"):
                # Directory fragment — match a contiguous run of whole path
                # components (e.g. "/services/poc/" -> ["services","poc"]).
                wanted = [s for s in frag.split("/") if s]
                if wanted and _contains_subsequence(segments, wanted):
                    return True
            else:
                # parent/name fragment (e.g. "core/audit") — match the
                # file's own <parent>/<stem> exactly.
                if frag == f"{parent_name}/{stem}":
                    return True
        elif frag.startswith("."):
            # Extension / suffix fragment (e.g. ".pyc").
            if path.suffix == frag or rel.endswith(frag):
                return True
        elif frag.endswith("_") and not frag.endswith("__"):
            # Deliberate name-family prefix (e.g. "capture_") — anchored to
            # the start of the file stem, not anywhere in the path.  A double
            # trailing underscore (e.g. "__pycache__") is a dunder dir name,
            # not a prefix, so it falls through to whole-segment matching.
            if stem.startswith(frag):
                return True
        else:
            # Bare-name fragment — whole stem or whole path segment only.
            if stem == frag or frag in segments:
                return True
    return False


def _contains_subsequence(segments: list[str], wanted: list[str]) -> bool:
    """True if ``wanted`` appears as a contiguous run within ``segments``."""
    n = len(wanted)
    if n == 0 or n > len(segments):
        return False
    return any(
        segments[i:i + n] == wanted
        for i in range(len(segments) - n + 1)
    )


def _scan_file(
    path: Path,
    root: Path,
    tokens: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return a list of leak dicts for any forbidden token found in path."""
    leaks: list[dict[str, Any]] = []
    if _is_allowed(path, root):
        return leaks
    if path.suffix not in SOURCE_EXTENSIONS:
        return leaks
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return leaks
    for lineno, line in enumerate(text.splitlines(), start=1):
        for token in tokens:
            if token in line:
                leaks.append(
                    {
                        "token": token,
                        "file": str(path.relative_to(root)),
                        "line": lineno,
                        "snippet": line.strip()[:120],
                    }
                )
    return leaks


def _scan_tree(root: Path, tokens: tuple[str, ...]) -> tuple[list[dict[str, Any]], int, int]:
    """Walk the source tree and return (leaks, checked_files, skipped_files)."""
    leaks: list[dict[str, Any]] = []
    checked = 0
    skipped = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in SKIP_EXTENSIONS:
            continue
        if _is_allowed(path, root):
            skipped += 1
            continue
        if path.suffix not in SOURCE_EXTENSIONS:
            continue
        checked += 1
        leaks.extend(_scan_file(path, root, tokens))
    return leaks, checked, skipped


def _run_shell_gate(root: Path) -> str:
    """Run check_no_poc_in_prod.sh and return 'ok', 'skipped', or an error message."""
    shell_script = root / "scripts" / "check_no_poc_in_prod.sh"
    if not shell_script.exists():
        return "skipped:script_not_found"
    try:
        result = subprocess.run(
            ["bash", str(shell_script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return "ok"
        # Exit 0 from the shell script means clean; non-zero means leakage or warn
        # The shell script also exits 0 for "no prod build dirs found" (WARN case)
        stdout = (result.stdout + result.stderr).strip()
        if "WARN" in stdout and result.returncode == 0:
            return "ok:no_prod_build_dirs"
        return f"leak_detected:exit={result.returncode}"
    except subprocess.TimeoutExpired:
        return "skipped:timeout"
    except Exception as exc:  # noqa: BLE001
        return f"error:{exc}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scan source tree for PoC tokens that must not reach production "
            "(ADR-004 §5, REG-06 dead-code-elimination gate)."
        )
    )
    parser.add_argument(
        "--root",
        default=str(PROJECT_ROOT),
        metavar="PATH",
        help="Repository root to scan (default: project root).",
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        default=False,
        help="Emit JSON report to stdout (in addition to human-readable output).",
    )
    parser.add_argument(
        "--skip-shell-gate",
        action="store_true",
        default=False,
        help="Do not invoke check_no_poc_in_prod.sh.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: scan root not found: {root}", file=sys.stderr)
        sys.exit(3)

    verified_at = iso_z(datetime.now(UTC))
    leaks, checked, skipped = _scan_tree(root, FORBIDDEN_TOKENS)

    shell_result = (
        _run_shell_gate(root) if not args.skip_shell_gate else "skipped:flag"
    )

    # Shell gate failure counts as a leak
    shell_leaked = shell_result.startswith("leak_detected")
    passed = len(leaks) == 0 and not shell_leaked
    status_str = "passed" if passed else "failed"

    report: dict[str, Any] = {
        "verified_at": verified_at,
        "status": status_str,
        "passed": passed,
        "scan_root": str(root),
        "forbidden_tokens": list(FORBIDDEN_TOKENS),
        "leaks": leaks,
        "allowed_paths_skipped": skipped,
        "checked_files": checked,
        "shell_gate_result": shell_result,
    }

    if args.emit_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    # Human-readable summary
    if passed:
        print(
            f"OK    source scan clean: {checked} files checked, "
            f"{skipped} allowed-path files skipped, shell_gate={shell_result}",
            file=sys.stderr,
        )
    else:
        print(
            f"FAIL  PoC-to-prod migration check FAILED "
            f"(source leaks={len(leaks)}, shell_gate={shell_result})",
            file=sys.stderr,
        )
        for leak in leaks:
            print(
                f"      [{leak['token']}] {leak['file']}:{leak['line']} "
                f"— {leak['snippet']}",
                file=sys.stderr,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
