#!/usr/bin/env python
"""v8_bfs_visitor.py — Stage 2 G2 deliverable (T101b + T102 + T108)

Playwright-based BFS visitor for v8 PRD state-graph-traversal.
Integrates:
  - T101: BFS traversal core (cell space from v8_cell_space.py)
  - T102: screenshot grid generator (per-cell PNG + meta.json)
  - T108: unreachable manifest populator (emits append-only YAML)

Run modes (--mode):
  full              — visit every reachable cell (cycle 1 launch, ~24h compute)
  sample N          — visit N random reachable cells (smoke test)
  unreachable-only  — emit unreachable manifest only, no Playwright launch
  dry-run           — classify + path-resolve, NO Playwright navigate, NO LLM

Output layout:
  {output_dir}/cycle_{N}/
    visited.jsonl                 — per-cell visit record (state_hash + meta)
    unreachable.jsonl             — per-cell unreachable record (reason + evidence)
    cells/{state_hash}.png        — screenshot per visited cell
    cells/{state_hash}.meta.json  — per-cell metadata (DOM extract, console errors)
    summary.json                  — accounting + timing

Dev credentials (per role): .env DEV_TEST_USER_{ROLE} or --creds-file fixture.
Required for protected routes login. Missing creds → dev_credential_missing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import random
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml  # type: ignore[import-untyped]

# Import cell space module (T101a)
SCRIPTS_DIR = (pathlib.Path(__file__).resolve().parents[1] / "scripts")
sys.path.insert(0, str(SCRIPTS_DIR))
from v8_cell_space import (  # noqa: E402
    ACCESS_RULES,
    Cell,
    ROUTE_ENTITY,
    ROUTE_TO_ROUTEKEY,
    Unreachable,
    classify_cell,
    generate_cell_space,
    load_exclude_manifest,
    load_ground_truth,
    load_interaction,
    resolve_slot,
)
import v8_state_hash as v8sh  # noqa: E402
from v8_detector_L1_banned_regex import scan_l1  # noqa: E402
from v8_detector_L3_format_consistency import scan_l3  # noqa: E402
from v8_detector_L4_cross_field import scan_l4  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = os.environ.get(
    "V8_BASE_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_WEB_PORT', '8000')}",
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".omc/state/v8-traversal"
UNREACHABLE_MANIFEST = REPO_ROOT / ".omc/state/v8-unreachable-manifest.yaml"

# Test entity IDs (real synthetic IDs from DB via v8_resolve_fixture_ids.py).
# Loaded at startup; falls back to placeholder constants if file missing.
FIXTURE_IDS_FILE = REPO_ROOT / ".omc/state/v8-fixture-ids.json"


def load_test_ids() -> dict[str, str]:
    if FIXTURE_IDS_FILE.exists():
        data: dict[str, Any] = json.loads(FIXTURE_IDS_FILE.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if v}
    return {
        "customerId": "SYN-CUSTOMER-001",
        "consultationId": "SYN-CONSULT-001",
        "houseViewId": "SYN-HV-001",
    }


TEST_IDS: dict[str, str] = load_test_ids()


# --------------------------------------------------------------------------
# Login fixtures — dev credentials per role (사용자 active input pending)
# --------------------------------------------------------------------------

def load_dev_credentials(creds_file: pathlib.Path | None) -> dict[str, dict[str, str]]:
    """Load per-role dev credentials.

    Resolution order:
      1. --creds-file YAML path (if given)
      2. Environment variables DEV_TEST_USER_{ROLE} = "email:password"
      3. Returns empty dict → roles with no creds yield dev_credential_missing.
    """
    creds: dict[str, dict[str, str]] = {}
    if creds_file is not None and creds_file.exists():
        with creds_file.open() as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
        for role, cred in data.items():
            if isinstance(cred, dict) and "email" in cred and "password" in cred:
                creds[role] = {"email": str(cred["email"]),
                                "password": str(cred["password"])}
    for role in ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"]:
        env_key = f"DEV_TEST_USER_{role}"
        raw = os.environ.get(env_key)
        if raw and ":" in raw and role not in creds:
            email, password = raw.split(":", 1)
            creds[role] = {"email": email, "password": password}
    return creds


# --------------------------------------------------------------------------
# Route URL concretizer — resolve :param patterns with synthetic IDs
# --------------------------------------------------------------------------

def concretize_url(route_pattern: str) -> str:
    url = route_pattern
    for param, value in TEST_IDS.items():
        url = url.replace(f":{param}", value)
    return url


# --------------------------------------------------------------------------
# state_hash via v8_state_hash module direct import (DELTA-N2 canonical)
# --------------------------------------------------------------------------

def compute_state_hash(
    cell: Cell,
    gt: dict[str, Any],
    visible_text: str = "",
) -> str:
    """Deterministic state hash for a cell (PRD §4 #2 4-axis + visible_text).

    Viewport is a separate dimension; the per-viewport screenshot path adds
    viewport to disambiguate physical files. The hash itself follows PRD §4 #2
    spec: sha256(route_pattern, role, content_state_enum, interaction_state,
    normalized_visible_text).
    """
    entity = ROUTE_ENTITY.get(cell.route) or "none"
    concrete_state = resolve_slot(gt, cell.route, cell.content_state) or "N_A"
    sh_cell = v8sh.Cell(
        route_pattern=cell.route,
        role=cell.role,
        content_state=f"{entity}#{concrete_state}",
        interaction_state=cell.interaction,
        visible_text=visible_text,
    )
    return v8sh.state_hash(sh_cell)


# --------------------------------------------------------------------------
# Visit record dataclass
# --------------------------------------------------------------------------

@dataclass
class VisitRecord:
    cell: Cell
    state_hash: str
    visited_at: str
    duration_ms: int
    screenshot_path: str
    console_errors: list[str] = field(default_factory=list)
    axe_violations: int = 0
    dom_text_excerpt: str = ""
    detector_findings: dict[str, list[str]] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Async BFS visitor (Playwright)
# --------------------------------------------------------------------------

class BFSVisitor:
    def __init__(
        self,
        cycle: int,
        output_dir: pathlib.Path,
        base_url: str,
        creds: dict[str, dict[str, str]],
        dry_run: bool = False,
    ) -> None:
        self.cycle = cycle
        self.output_dir = output_dir / f"cycle_{cycle}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "cells").mkdir(exist_ok=True)
        self.base_url = base_url
        self.creds = creds
        self.dry_run = dry_run
        self.visited_fh = (self.output_dir / "visited.jsonl").open("a", encoding="utf-8")
        self.unreachable_fh = (self.output_dir / "unreachable.jsonl").open(
            "a", encoding="utf-8"
        )
        self.gt = load_ground_truth()
        self.start_ts = time.time()
        self.visited_count = 0
        self.unreachable_count = 0
        self.skipped_resume = 0
        # Resume dedup: seed already-emitted unreachable cell_ids from the
        # existing append-mode unreachable.jsonl so each cell is emitted at
        # most once across runs (otherwise classify-time re-emits double the
        # file, breaking write_unreachable_manifest() / 40320 SoT accounting).
        self.emitted_unreachable: set[str] = self._load_emitted_unreachable()

    def __enter__(self) -> "BFSVisitor":
        return self

    def __exit__(self, *exc: object) -> None:
        self.visited_fh.close()
        self.unreachable_fh.close()

    def load_resume(self) -> set[str]:
        """Read visited.jsonl to collect already-visited cell_ids for resume."""
        seen: set[str] = set()
        visited_path = self.output_dir / "visited.jsonl"
        if not visited_path.exists():
            return seen
        with visited_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec: dict[str, Any] = json.loads(line)
                    cell_data: dict[str, Any] = rec["cell"]
                    cell_id = Cell(**cell_data).cell_id()
                    seen.add(cell_id)
                except Exception:
                    continue
        return seen

    def _load_emitted_unreachable(self) -> set[str]:
        """Read existing unreachable.jsonl to collect already-emitted cell_ids.

        Seeds the resume dedup set so emit_unreachable() skips cells already
        recorded by a prior run (the file is opened in append mode).
        """
        seen: set[str] = set()
        path = self.output_dir / "unreachable.jsonl"
        if not path.exists():
            return seen
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec: dict[str, Any] = json.loads(line)
                    cid = rec.get("cell_id")
                    if cid is None:
                        cid = Cell(**rec["cell"]).cell_id()
                    seen.add(cid)
                except Exception:
                    continue
        return seen

    async def visit_cell(self, page: Any, cell: Cell) -> VisitRecord:
        """Navigate + screenshot + state_hash for a reachable cell.

        Auth race fix: AuthSessionRestorer (apps/web/src/lib/api.ts:51-71)
        refreshes the in-memory zustand access_token from the HttpOnly refresh
        cookie *asynchronously* after mount. networkidle may settle before that
        refresh completes; ProtectedRoute then redirects to /login.
        We wait an additional ~700ms post-navigate and retry once if the page
        shows the /login marker.
        """
        t0 = time.time()
        url = self.base_url + concretize_url(cell.route)
        visible_text = ""
        if not self.dry_run:
            await page.set_viewport_size(self._viewport_dims(cell.viewport))
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Give AuthSessionRestorer time to refresh access_token from cookie
            await page.wait_for_timeout(700)
            try:
                visible_text = await page.locator("body").text_content(timeout=5000)
                visible_text = (visible_text or "")[:5000]
            except Exception:
                visible_text = ""
            # Retry once if we landed on /login despite valid session
            if "직원 로그인" in visible_text[:300] and "보호된" in visible_text[:300]:
                try:
                    await page.reload(wait_until="networkidle", timeout=15000)
                    await page.wait_for_timeout(1000)
                    visible_text = await page.locator("body").text_content(timeout=5000)
                    visible_text = (visible_text or "")[:5000]
                except Exception:
                    pass
        sh = compute_state_hash(cell, self.gt, visible_text)
        # Per-viewport screenshot path: {state_hash}_{viewport}.png
        screenshot_rel = f"cells/{sh}_{cell.viewport}.png"
        screenshot_path = self.output_dir / screenshot_rel
        if not self.dry_run:
            await page.screenshot(path=str(screenshot_path), full_page=True)
        # Inline deterministic detectors (L1/L3/L4) — no LLM cost
        l1 = scan_l1(visible_text) if visible_text else []
        l3 = scan_l3(visible_text) if visible_text else []
        l4 = scan_l4({})  # L4 requires entity-bound fields; populated by BFS post-pass
        # Role-aware exemption — DevReference component (apps/web/src/components/
        # DevReference.tsx ALLOWED_ROLES={"ADMIN"}) intentionally exposes
        # ADR-###/REG-0#/W#-T# identifiers to ADMIN only. PRD §1.1 BANNED comment
        # line 18: "ADMIN/AUDIT_VIEWER role-gated 표시가 필요한 식별자". ADMIN
        # surface is the intended target — these findings are not defects.
        if cell.role == "ADMIN":
            l1 = [f for f in l1 if f.pattern_name != "BANNED_INTERNAL_ID"]
        detector_findings: dict[str, list[str]] = {
            "L1": [f"{f.pattern_name}@{f.offset}:{f.match_text[:50]}" for f in l1],
            "L3": [f"{f.category}/{f.pattern_name}@{f.offset}:{f.match_text[:50]}" for f in l3],
            "L4": [f"{f.combo_id}" for f in l4],
        }
        duration_ms = int((time.time() - t0) * 1000)
        return VisitRecord(
            cell=cell,
            state_hash=sh,
            visited_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            duration_ms=duration_ms,
            screenshot_path=screenshot_rel,
            dom_text_excerpt=visible_text[:500],
            detector_findings=detector_findings,
        )

    @staticmethod
    def _viewport_dims(name: str) -> dict[str, int]:
        return {
            "desktop_wide": {"width": 1440, "height": 900},
            "desktop_narrow": {"width": 1280, "height": 720},
            "tablet": {"width": 768, "height": 1024},
            "mobile": {"width": 375, "height": 812},
        }[name]

    async def login_role(self, page: Any, role: str) -> bool:
        """Login as the given role. Returns False if creds missing."""
        if role not in self.creds:
            return False
        cred = self.creds[role]
        if not self.dry_run:
            await page.goto(self.base_url + "/login", timeout=30000)
            await page.fill('input[type="email"]', cred["email"])
            await page.fill('input[type="password"]', cred["password"])
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/dashboard", timeout=15000)
        return True

    def emit_unreachable(self, u: Unreachable) -> None:
        cid = u.cell.cell_id()
        if cid in self.emitted_unreachable:
            # Already emitted (this run or a prior resumed run) — dedup so
            # the append-mode file is not doubled on re-run.
            return
        self.emitted_unreachable.add(cid)
        self.unreachable_count += 1
        self.unreachable_fh.write(json.dumps({
            "cell": asdict(u.cell),
            "cell_id": u.cell.cell_id(),
            "reason": u.reason,
            "evidence_file_line": u.evidence,
            "confidence": u.confidence,
            "marked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "marked_by_worker": "v8_bfs_visitor.py",
        }, ensure_ascii=False) + "\n")

    def emit_visit(self, rec: VisitRecord) -> None:
        self.visited_count += 1
        self.visited_fh.write(json.dumps({
            "cell": asdict(rec.cell),
            "cell_id": rec.cell.cell_id(),
            "state_hash": rec.state_hash,
            "visited_at": rec.visited_at,
            "duration_ms": rec.duration_ms,
            "screenshot_path": rec.screenshot_path,
            "console_errors": rec.console_errors,
            "axe_violations": rec.axe_violations,
            "dom_text_excerpt": rec.dom_text_excerpt[:500],
            "detector_findings": rec.detector_findings,
        }, ensure_ascii=False) + "\n")

    async def run(
        self,
        cells_to_visit: Iterable[Cell],
        max_cells: int | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        already = self.load_resume() if resume else set()
        self.skipped_resume = 0

        if self.dry_run:
            count = 0
            for cell in cells_to_visit:
                if cell.cell_id() in already:
                    self.skipped_resume += 1
                    continue
                rec = await self.visit_cell(None, cell)
                self.emit_visit(rec)
                count += 1
                if max_cells is not None and count >= max_cells:
                    break
            return self._finalize_summary()

        # Real Playwright launch (delayed import — only if needed)
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "Playwright not installed in current python env. "
                "Expected: /opt/conda/envs/playwright. Re-run with that env."
            ) from e

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                count = 0
                current_role: str | None = None
                page = None
                for cell in cells_to_visit:
                    if cell.cell_id() in already:
                        self.skipped_resume += 1
                        continue
                    if cell.role != current_role or page is None:
                        if page is not None:
                            await page.close()
                        context = await browser.new_context()
                        page = await context.new_page()
                        ok = await self.login_role(page, cell.role)
                        if not ok:
                            self.emit_unreachable(Unreachable(
                                cell, "dev_credential_missing",
                                f".env DEV_TEST_USER_{cell.role} missing or --creds-file lacks {cell.role}",
                            ))
                            continue
                        current_role = cell.role
                    try:
                        rec = await self.visit_cell(page, cell)
                        # Login redirect detection — ProtectedRoute rejected
                        # cell (synthetic data ID may exist but role lacks
                        # access, OR fetch returned 404 redirect to /login)
                        excerpt_head = rec.dom_text_excerpt[:200]
                        # RBAC 403 ForbiddenPage — apps/web/src/pages/
                        # ForbiddenPage.tsx renders "403" + "권한이 없습니다."
                        # when ProtectedRoute correctly denies the role. This is
                        # a control SUCCESS (access_denied), NOT a flow failure.
                        if "권한이 없습니다" in excerpt_head:
                            self.emit_unreachable(Unreachable(
                                cell, "access_denied",
                                f"ForbiddenPage (403) rendered for role {cell.role} "
                                f"on route {cell.route}: RBAC denied as designed",
                                confidence="HIGH",
                            ))
                        elif (
                            "직원 로그인" in excerpt_head
                            and "보호된" in excerpt_head
                        ):
                            self.emit_unreachable(Unreachable(
                                cell, "flow_blocking",
                                f"login_redirect: route {cell.route} returned /login page after auth",
                                confidence="MEDIUM",
                            ))
                        else:
                            self.emit_visit(rec)
                    except Exception as e:
                        self.emit_unreachable(Unreachable(
                            cell, "flow_blocking",
                            f"runtime exception: {type(e).__name__}: {e!s:.200}",
                            confidence="MEDIUM",
                        ))
                    count += 1
                    if max_cells is not None and count >= max_cells:
                        break
            finally:
                await browser.close()
        return self._finalize_summary()

    def _finalize_summary(self) -> dict[str, Any]:
        elapsed_s = int(time.time() - self.start_ts)
        summary = {
            "cycle": self.cycle,
            "visited_count": self.visited_count,
            "unreachable_count": self.unreachable_count,
            "skipped_resume": self.skipped_resume,
            "elapsed_seconds": elapsed_s,
            "output_dir": str(self.output_dir),
        }
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return summary


# --------------------------------------------------------------------------
# Unreachable manifest YAML writer (T108)
# --------------------------------------------------------------------------

def write_unreachable_manifest(
    cycle: int,
    output_dir: pathlib.Path,
    manifest_path: pathlib.Path = UNREACHABLE_MANIFEST,
) -> dict[str, Any]:
    """Convert {output_dir}/cycle_N/unreachable.jsonl + classify_cell pass
    results → v8-unreachable-manifest.yaml population.

    The manifest is the SoT for L_detector 100% accounting (DELTA-3 / C3).
    """
    jsonl_path = output_dir / f"cycle_{cycle}" / "unreachable.jsonl"
    if not jsonl_path.exists():
        return {"updated": False, "reason": "no unreachable.jsonl"}

    entries: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue

    with manifest_path.open() as fh:
        manifest: dict[str, Any] = yaml.safe_load(fh)

    manifest["unreachable_cells"] = entries
    manifest["total_entries"] = len(entries)
    manifest["populated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["last_populated_by"] = f"v8_bfs_visitor.py cycle {cycle}"
    with manifest_path.open("w") as fh:
        yaml.safe_dump(manifest, fh, allow_unicode=True, sort_keys=False)

    return {"updated": True, "entries": len(entries), "manifest": str(manifest_path)}


# --------------------------------------------------------------------------
# CLI entry
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v8 BFS visitor (Playwright)")
    p.add_argument("--cycle", type=int, required=True, help="cycle number (1-3)")
    p.add_argument(
        "--mode",
        choices=["full", "sample", "unreachable-only", "dry-run"],
        default="dry-run",
        help="execution mode (default: dry-run)",
    )
    p.add_argument("--max-cells", type=int, default=None,
                   help="cap reachable cells (smoke test)")
    p.add_argument("--sample-size", type=int, default=10,
                   help="sample mode: random sample size")
    p.add_argument("--seed", type=int, default=42,
                   help="random seed for sample mode (determinism)")
    p.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--creds-file", type=pathlib.Path, default=None,
                   help="YAML mapping role → {email, password}")
    p.add_argument("--no-resume", action="store_true",
                   help="ignore existing visited.jsonl, restart from scratch")
    p.add_argument("--populate-manifest", action="store_true",
                   help="after run, write unreachable.jsonl → v8-unreachable-manifest.yaml")
    args = p.parse_args(argv)

    gt = load_ground_truth()
    inter = load_interaction()
    _exclude = load_exclude_manifest()  # validate file exists; populated cells filtered upstream

    creds = load_dev_credentials(args.creds_file)

    # Split into reachable / unreachable
    all_cells = list(generate_cell_space(gt, inter))
    reachable: list[Cell] = []
    unreachables: list[Unreachable] = []
    for cell in all_cells:
        u = classify_cell(cell, gt)
        if u is None:
            reachable.append(cell)
        else:
            unreachables.append(u)

    with BFSVisitor(
        cycle=args.cycle,
        output_dir=args.output_dir,
        base_url=args.base_url,
        creds=creds,
        dry_run=(args.mode == "dry-run"),
    ) as visitor:
        # Emit all classify-time unreachables first
        for u in unreachables:
            visitor.emit_unreachable(u)

        if args.mode == "unreachable-only":
            summary = visitor._finalize_summary()
        else:
            cells_to_visit: list[Cell]
            if args.mode == "sample":
                rng = random.Random(args.seed)
                cells_to_visit = rng.sample(reachable, min(args.sample_size, len(reachable)))
            else:
                cells_to_visit = reachable
            summary = asyncio.run(visitor.run(
                cells_to_visit=cells_to_visit,
                max_cells=args.max_cells,
                resume=not args.no_resume,
            ))

    print(json.dumps({
        "mode": args.mode,
        "cycle": args.cycle,
        "reachable_total": len(reachable),
        "unreachable_total_pre_runtime": len(unreachables),
        "summary": summary,
    }, indent=2, ensure_ascii=False))

    if args.populate_manifest:
        result = write_unreachable_manifest(args.cycle, args.output_dir)
        print(json.dumps({"manifest_update": result}, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
