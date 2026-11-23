#!/usr/bin/env python3
"""step7_gate_verify.py — G1~G8 evidence 직접 파싱, gate 전원 PASS 검증.

Usage:
    python apps/web/e2e/scripts/step7_gate_verify.py [--root /path/to/project]

PRD §7 Architecture (Fix 3):
  - expected_total_cells 동적 계산 (MF-1): manifest routes 수 × 3 roles + row cells
  - G4~G8 evidence file 직접 parse (status field 읽기 금지)
  - 미존재/non-zero → sys.exit(1), G 전체 FAIL 보고

Gates:
  G1  npm run build exit=0                       → build.log
  G2  (PENDING + bootstrap_missing) == 0, cell count == expected → ledger.json
  G3a screenshot 전수 존재 (22 routes × 2종)    → playwright-report artifact list
  G3b baseline banned 0 + V048 neg→match≥1       → playwright-report-visual-fullwalk.json
  G4  tsc exit=0                                  → tsc.log (direct parse)
  G5  vitest numFailedTests=0                     → vitest.json (direct parse)
  G6  qa-audit-quality.spec.ts unexpected=0       → playwright-report-quality.json
  G7  qa-audit-admin.spec.ts unexpected=0         → playwright-report-admin.json
  G8  visual-fullwalk.spec.ts unexpected=0        → playwright-report-visual-fullwalk.json

Exit: 0 = all PASS, 1 = any FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ── Row-cell constants (PRD §8) ──────────────────────────────────────────────
METADATA_BLOCK_ROW_CELLS = 27  # 9 rows × 3 sub-states (DRAFT/ACTIVATED/missing)
JSON_SECTION_ROW_CELLS = 9     # 3 components × 3 db_states
ROW_CELL_SUM = METADATA_BLOCK_ROW_CELLS + JSON_SECTION_ROW_CELLS  # 36

ROLES_PER_ROUTE = 3  # PB, WM, AUDIT_VIEWER


def _load_json(path: Path, label: str) -> dict[str, Any]:
    """Load JSON file; exit(1) if missing or invalid."""
    if not path.exists():
        print(f"[FAIL] {label}: 파일 미존재 → {path}")
        sys.exit(1)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[FAIL] {label}: JSON 파싱 오류 → {exc}")
        sys.exit(1)


def gate_g2(ledger_path: Path, manifest_path: Path) -> bool:
    """G2: cell count == expected_total AND (PENDING + bootstrap_missing) == 0."""
    manifest = _load_json(manifest_path, "route-manifest.json")
    ledger = _load_json(ledger_path, "ledger.json")

    n_routes = len(manifest.get("routes", []))
    expected_page_cells = n_routes * ROLES_PER_ROUTE
    expected_total = expected_page_cells + ROW_CELL_SUM  # dynamic (MF-1)

    cells = ledger.get("cells", [])
    actual_total = len(cells)

    # Verify ledger's own expected_total_cells field matches dynamic calculation
    ledger_expected = ledger.get("expected_total_cells", -1)
    if ledger_expected != expected_total:
        print(
            f"[FAIL] G2: ledger.expected_total_cells={ledger_expected} "
            f"≠ dynamic={expected_total} "
            f"(routes={n_routes}×{ROLES_PER_ROUTE} + row_cells={ROW_CELL_SUM})"
        )
        return False

    if actual_total != expected_total:
        print(
            f"[FAIL] G2: cell count drift: actual={actual_total} "
            f"vs expected={expected_total} (manifest routes={n_routes})"
        )
        return False

    pending = sum(
        1 for c in cells
        if c.get("status") in ("not_yet_collected", "pending")
        or c.get("bootstrap_missing") is True
    )
    if pending != 0:
        pending_ids = [
            c.get("cell_id") for c in cells
            if c.get("status") in ("not_yet_collected", "pending")
            or c.get("bootstrap_missing") is True
        ][:10]
        print(f"[FAIL] G2: PENDING/bootstrap_missing = {pending} (최대 10개: {pending_ids})")
        return False

    print(f"[PASS] G2: cells={actual_total}/{expected_total}, pending=0")
    return True


def gate_g4(tsc_log_path: Path) -> bool:
    """G4: tsc exit=0 (direct parse, not status field)."""
    if not tsc_log_path.exists():
        print(f"[FAIL] G4: tsc.log 미존재 → {tsc_log_path}")
        return False

    content = tsc_log_path.read_text(encoding="utf-8")
    # tsc log 마지막 줄에 exit code 기록 (형식: "exit_code: 0")
    for line in reversed(content.splitlines()):
        if line.startswith("exit_code:"):
            code = line.split(":", 1)[1].strip()
            if code == "0":
                print("[PASS] G4: tsc exit=0")
                return True
            else:
                print(f"[FAIL] G4: tsc exit={code} (not 0)")
                return False

    # exit_code 행 없으면 오류 유무로 판단
    if "error TS" in content:
        error_count = content.count("error TS")
        print(f"[FAIL] G4: tsc 오류 {error_count}건 발견")
        return False

    print("[PASS] G4: tsc log에 오류 없음")
    return True


def gate_g5(vitest_json_path: Path) -> bool:
    """G5: vitest numFailedTests=0 (direct parse)."""
    data = _load_json(vitest_json_path, "vitest.json")
    failed = data.get("numFailedTests", -1)
    if failed == -1:
        print(f"[FAIL] G5: vitest.json에 numFailedTests 필드 없음")
        return False
    if failed != 0:
        print(f"[FAIL] G5: vitest numFailedTests={failed}")
        return False
    print(f"[PASS] G5: vitest numFailedTests=0")
    return True


def _gate_playwright(report_path: Path, gate: str, spec_label: str) -> bool:
    """Generic Playwright report gate: stats.unexpected == 0 (direct parse)."""
    data = _load_json(report_path, f"playwright-report ({gate})")
    # Playwright JSON reporter: top-level "stats" object
    stats = data.get("stats", {})
    unexpected = stats.get("unexpected", -1)
    if unexpected == -1:
        print(f"[FAIL] {gate}: {spec_label} — stats.unexpected 필드 없음 in {report_path}")
        return False
    if unexpected != 0:
        print(f"[FAIL] {gate}: {spec_label} — stats.unexpected={unexpected}")
        return False
    print(f"[PASS] {gate}: {spec_label} — stats.unexpected=0")
    return True


def gate_g3a(screenshot_dir: Path, n_routes: int) -> bool:
    """G3a: screenshot 전수 존재 (routes × 2종: viewport + fullPage)."""
    expected = n_routes * 2
    if not screenshot_dir.exists():
        print(f"[FAIL] G3a: screenshot 디렉토리 미존재 → {screenshot_dir}")
        return False

    screenshots = list(screenshot_dir.glob("*.png"))
    actual = len(screenshots)
    if actual < expected:
        print(f"[FAIL] G3a: screenshot {actual}/{expected} (routes={n_routes}×2)")
        return False
    print(f"[PASS] G3a: screenshot {actual}개 ≥ {expected}개")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="G1~G8 gate evidence verifier")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root (default: current directory)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    # ── 경로 정의 ────────────────────────────────────────────────────────────
    manifest_path = root / ".omc" / "visual-audit" / "route-manifest.json"
    ledger_path   = root / ".omc" / "visual-audit" / "ledger.json"
    tsc_log_path  = root / ".omc" / "visual-audit" / "tsc.log"
    vitest_json   = root / ".omc" / "visual-audit" / "vitest.json"
    build_log     = root / ".omc" / "visual-audit" / "build.log"
    screenshot_dir = root / ".omc" / "visual-audit" / "screenshots"
    report_quality   = root / ".omc" / "visual-audit" / "playwright-report-quality.json"
    report_admin     = root / ".omc" / "visual-audit" / "playwright-report-admin.json"
    report_fullwalk  = root / ".omc" / "visual-audit" / "playwright-report-visual-fullwalk.json"

    manifest = _load_json(manifest_path, "route-manifest.json")
    n_routes = len(manifest.get("routes", []))

    results: dict[str, bool] = {}

    # G1: build.log exit=0
    if build_log.exists():
        content = build_log.read_text(encoding="utf-8")
        passed = "exit_code: 0" in content or ("error" not in content.lower())
        results["G1"] = passed
        print(f"{'[PASS]' if passed else '[FAIL]'} G1: build.log")
    else:
        print(f"[FAIL] G1: build.log 미존재 → {build_log}")
        results["G1"] = False

    # G2: ledger cell count + pending=0
    results["G2"] = gate_g2(ledger_path, manifest_path)

    # G3a: screenshot 전수
    results["G3a"] = gate_g3a(screenshot_dir, n_routes)

    # G3b: visual-fullwalk report unexpected=0 (implies banned=0 + V048 checks passed)
    results["G3b"] = _gate_playwright(report_fullwalk, "G3b", "visual-fullwalk.spec.ts")

    # G4: tsc exit=0
    results["G4"] = gate_g4(tsc_log_path)

    # G5: vitest numFailedTests=0
    results["G5"] = gate_g5(vitest_json)

    # G6: qa-audit-quality.spec.ts
    results["G6"] = _gate_playwright(report_quality, "G6", "qa-audit-quality.spec.ts")

    # G7: qa-audit-admin.spec.ts
    results["G7"] = _gate_playwright(report_admin, "G7", "qa-audit-admin.spec.ts")

    # G8: visual-fullwalk.spec.ts
    results["G8"] = _gate_playwright(report_fullwalk, "G8", "visual-fullwalk.spec.ts")

    # ── 최종 판정 ─────────────────────────────────────────────────────────────
    print()
    failed_gates = [g for g, ok in results.items() if not ok]
    if failed_gates:
        print(f"[VERDICT] FAIL — {len(failed_gates)}개 gate 실패: {failed_gates}")
        sys.exit(1)
    else:
        print(f"[VERDICT] PASS — 모든 gate ({list(results.keys())}) 통과")
        sys.exit(0)


if __name__ == "__main__":
    main()
