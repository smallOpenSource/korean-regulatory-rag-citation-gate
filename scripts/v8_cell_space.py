#!/usr/bin/env python
"""v8_cell_space.py — Stage 2 G2 deliverable (T101a)

Cell space generator + reachability filter for v8 PRD state-graph-traversal.
Pure logic, no browser. Importable by v8_bfs_visitor.py.

Cardinality (immutable, ground-truth.yaml LOCKED):
  ROUTES_PROTECTED × ROLES × CONTENT_STATES × INTERACTION_CLASSES × VIEWPORTS
  = 21 × 5 × 8 × 12 × 4 = 40,320 cells (N_VIEWPORT_EXT)

CONTENT_STATES axis design (PRD §3.7.0):
  Cardinality 8 = max per-entity state count (house_views has 8 states).
  Axis encoded as positional slots S0-S7. Per route's bound entity:
    - entity has N states → S0..S(N-1) reachable, S_N..S7 unreachable
    - no entity binding → only S0 reachable, S1..S7 unreachable
  BFS visitor resolves S_n → actual entity enum at navigation time.

Reachability filter (8 unreachable reasons enum from v8-unreachable-manifest.yaml):
  - access_denied               (RBAC reject via access_rules mirror of access.ts)
  - pre_auth_only               (NOT applicable: only /login and /403, excluded from 21)
  - interaction_class_not_implemented  (interaction.yaml grep_hits=0 + route mismatch)
  - browser_unsupported         (touchgesture on desktop chromium)
  - viewport_unsupported        (mobile-only / desktop-only viewport mismatch)
  - dev_credential_missing      (role login fixture missing — runtime detect)
  - flow_blocking               (excluded endpoint dependency)
  - content_state_unreachable   (route × entity content_state slot mismatch)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Iterator
from dataclasses import dataclass, asdict
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GROUND_TRUTH = REPO_ROOT / ".omc/state/v8-ground-truth.yaml"
INTERACTION = REPO_ROOT / ".omc/state/v8-interaction.yaml"
EXCLUDE_MANIFEST = REPO_ROOT / ".omc/state/v8-exclude-manifest.yaml"

# 8 positional content_state slots (CONTENT_STATES axis cardinality = 8)
CONTENT_STATE_SLOTS: list[str] = [f"S{i}" for i in range(8)]


# --------------------------------------------------------------------------
# SoT loaders (single source of truth — read from LOCKED state files only)
# --------------------------------------------------------------------------

def load_ground_truth() -> dict[str, Any]:
    with GROUND_TRUTH.open() as fh:
        gt: dict[str, Any] = yaml.safe_load(fh)
    if gt.get("lock_status") != "LOCKED-cycle-1-baseline":
        raise RuntimeError(
            f"v8-ground-truth.yaml lock_status != LOCKED-cycle-1-baseline; "
            f"got {gt.get('lock_status')!r}. Stage 2 entry blocked."
        )
    return gt


def load_interaction() -> dict[str, Any]:
    with INTERACTION.open() as fh:
        return yaml.safe_load(fh)


def load_exclude_manifest() -> dict[str, Any]:
    with EXCLUDE_MANIFEST.open() as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------
# Access rules — mirror of apps/web/src/lib/access.ts:3-25
# 20 routeKey entries (1 protected URL is orphan: /house-views/:houseViewId)
# --------------------------------------------------------------------------

ACCESS_RULES: dict[str, list[str]] = {
    "dashboard": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "customers": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "customer360": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "consultation": ["PB", "WM"],
    "nba": ["PB", "WM"],
    "aftercare": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "emailDrafts": ["PB", "WM"],
    "houseViews": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "houseViewActivation": ["ADMIN"],
    "rag": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "batch": ["ADMIN"],
    "audit": ["ADMIN", "AUDIT_VIEWER"],
    "auditViewer": ["ADMIN", "AUDIT_VIEWER"],
    "rightsNotice": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "disputeCase": ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
    "aiModelCards": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "aiPolicy": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "koreanAIAct": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "aiAdminDashboard": ["ADMIN"],
    "quarantine": ["ADMIN"],
    "autopilotDemo": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
}

# Route URL → routeKey mapping (App.tsx:46-75 inspection).
# 21 protected URL patterns → 20 routeKeys.
# /house-views/:houseViewId reuses "houseViews" routeKey (Critic iter 2 M5
# orphan candidate; treated as houseViews access for cycle 1).
ROUTE_TO_ROUTEKEY: dict[str, str] = {
    "/dashboard": "dashboard",
    "/customers": "customers",
    "/customers/:customerId": "customer360",
    "/consultations/:consultationId": "consultation",
    "/nba": "nba",
    "/aftercare": "aftercare",
    "/email-drafts": "emailDrafts",
    "/house-views": "houseViews",
    "/house-views/:houseViewId": "houseViews",
    "/house-views/:houseViewId/activate": "houseViewActivation",
    "/rag": "rag",
    "/batch": "batch",
    "/audit": "audit",
    "/quarantine": "quarantine",
    "/audit-viewer": "auditViewer",
    "/rights-notice": "rightsNotice",
    "/dispute-cases": "disputeCase",
    "/ai-model-cards": "aiModelCards",
    "/ai-policy": "aiPolicy",
    "/korean-ai-act": "koreanAIAct",
    "/ai-admin-dashboard": "aiAdminDashboard",
}

# Route → bound entity (None means no content_state lifecycle; only slot S0).
ROUTE_ENTITY: dict[str, str | None] = {
    "/dashboard": None,
    "/customers": None,
    "/customers/:customerId": None,
    "/consultations/:consultationId": "consultations",
    "/nba": "nba_actions",
    "/aftercare": "aftercare_events",
    "/email-drafts": "email_drafts",
    "/house-views": "house_views",
    "/house-views/:houseViewId": "house_views",
    "/house-views/:houseViewId/activate": "house_views",
    "/rag": None,
    "/batch": "batch_jobs",
    "/audit": None,
    "/quarantine": None,
    "/audit-viewer": None,
    "/rights-notice": None,
    "/dispute-cases": None,
    "/ai-model-cards": None,
    "/ai-policy": None,
    "/korean-ai-act": None,
    "/ai-admin-dashboard": None,
}


# --------------------------------------------------------------------------
# Cell dataclass
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    route: str
    role: str
    content_state: str  # one of CONTENT_STATE_SLOTS
    interaction: str
    viewport: str

    def cell_id(self) -> str:
        # 5-tuple canonical with U+001F separator (DELTA-N2 state_hash compat)
        return "\x1f".join([
            self.route, self.role, self.content_state,
            self.interaction, self.viewport,
        ])


@dataclass
class Unreachable:
    cell: Cell
    reason: str
    evidence: str
    confidence: str = "HIGH"


# --------------------------------------------------------------------------
# Slot → concrete entity state resolver (BFS visitor uses this for navigation)
# --------------------------------------------------------------------------

def resolve_slot(gt: dict[str, Any], route: str, slot: str) -> str | None:
    """Map slot (S0..S7) → concrete entity state string for the given route.

    Returns:
        Entity state string (e.g., "DRAFT") if slot is valid for route's entity.
        "N_A" if route has no entity binding and slot == S0.
        None if slot is unreachable for this route.
    """
    entity = ROUTE_ENTITY.get(route)
    if entity is None:
        return "N_A" if slot == "S0" else None
    states: list[str] = gt["CONTENT_STATES"]["enumeration_per_entity"].get(entity, [])
    idx = int(slot[1:])
    if 0 <= idx < len(states):
        return states[idx]
    return None


# --------------------------------------------------------------------------
# Cell space generation (cartesian product 40,320)
# --------------------------------------------------------------------------

def generate_cell_space(gt: dict[str, Any], interaction: dict[str, Any]) -> Iterator[Cell]:
    routes: list[str] = gt["ROUTES_PROTECTED"]["enumeration"]
    roles: list[str] = gt["ROLES"]["enumeration"]
    interactions: list[str] = [c["name"] for c in interaction["classes"]]
    viewports: list[str] = [v["name"] for v in gt["VIEWPORTS"]["enumeration"]]
    for route in routes:
        for role in roles:
            for slot in CONTENT_STATE_SLOTS:
                for inter in interactions:
                    for vp in viewports:
                        yield Cell(route, role, slot, inter, vp)


# --------------------------------------------------------------------------
# Reachability filter — classify each cell as reachable or unreachable+reason
# --------------------------------------------------------------------------

UNIMPLEMENTED_INTERACTIONS = {"contextmenu", "drop", "paste", "touchgesture"}

# Routes where each interaction class is present (derived from v8-interaction.yaml
# entries inspection). If route not in this set for class c, the class is
# absent on that route → interaction_class_not_implemented.
INTERACTION_ROUTE_PRESENT: dict[str, set[str]] = {
    "keyboard": set(ROUTE_TO_ROUTEKEY.keys()),  # Layout-level tab + Escape
    "click": set(ROUTE_TO_ROUTEKEY.keys()),     # Layout buttons + page actions
    "modal": set(ROUTE_TO_ROUTEKEY.keys()),     # PoCAutoApprovalBadge via Layout
    "drag": {"/consultations/:consultationId"},  # ResizablePanels
    "aria-live": {
        "/rights-notice", "/ai-model-cards", "/nba",
        "/audit-viewer", "/customers/:customerId",
    },
    "websocket": {"/nba", "/consultations/:consultationId"},
    "contextmenu": set(),
    "drop": set(),
    "paste": set(),
    "touchgesture": set(),
    "focustrap": set(ROUTE_TO_ROUTEKEY.keys()),  # aria-modal via Layout
    "form-state": {
        "/house-views", "/house-views/:houseViewId",
        "/house-views/:houseViewId/activate",
        "/rag", "/audit-viewer", "/ai-model-cards",
        "/aftercare", "/consultations/:consultationId",
        "/rights-notice", "/email-drafts", "/customers",
        "/customers/:customerId",
    },
}


def classify_cell(cell: Cell, gt: dict[str, Any]) -> Unreachable | None:
    """Return Unreachable instance if cell is not reachable, else None."""
    routekey = ROUTE_TO_ROUTEKEY.get(cell.route)
    if routekey is None:
        return Unreachable(
            cell, "access_denied",
            f"route {cell.route} has no routeKey mapping",
        )
    allowed_roles: list[str] = ACCESS_RULES.get(routekey, [])
    if cell.role not in allowed_roles:
        return Unreachable(
            cell, "access_denied",
            f"access.ts ACCESS_RULES[{routekey!r}]={allowed_roles}",
        )

    # content_state slot filter
    concrete = resolve_slot(gt, cell.route, cell.content_state)
    if concrete is None:
        entity = ROUTE_ENTITY.get(cell.route)
        if entity is None:
            return Unreachable(
                cell, "content_state_unreachable",
                f"route {cell.route} has no entity; only slot S0 reachable",
            )
        states: list[str] = gt["CONTENT_STATES"]["enumeration_per_entity"].get(entity, [])
        return Unreachable(
            cell, "content_state_unreachable",
            f"entity {entity} has {len(states)} states; slot {cell.content_state} > S{len(states)-1}",
        )

    # interaction class filter
    if cell.interaction in UNIMPLEMENTED_INTERACTIONS:
        return Unreachable(
            cell, "interaction_class_not_implemented",
            f"v8-interaction.yaml class {cell.interaction!r} grep_hits=0",
        )
    routes_with_inter = INTERACTION_ROUTE_PRESENT.get(cell.interaction, set())
    if cell.route not in routes_with_inter:
        return Unreachable(
            cell, "interaction_class_not_implemented",
            f"interaction {cell.interaction!r} not present on route {cell.route}",
        )

    # viewport filter
    if cell.interaction == "drag" and cell.viewport in {"mobile", "tablet"}:
        return Unreachable(
            cell, "viewport_unsupported",
            f"interaction drag uses onMouseDown; viewport {cell.viewport} is touch-first",
        )

    return None


# --------------------------------------------------------------------------
# CLI entry — emit summary + JSONL stream
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v8 cell space generator + filter")
    p.add_argument("--output", type=pathlib.Path, default=None,
                   help="optional JSONL output path (default: stdout summary only)")
    p.add_argument("--summary-only", action="store_true",
                   help="emit summary counts only, no per-cell JSONL")
    args = p.parse_args(argv)

    gt = load_ground_truth()
    inter = load_interaction()

    total = 0
    reachable = 0
    unreachable_by_reason: dict[str, int] = {}

    out_fh = None
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        out_fh = args.output.open("w", encoding="utf-8")

    for cell in generate_cell_space(gt, inter):
        total += 1
        u = classify_cell(cell, gt)
        if u is None:
            reachable += 1
            if out_fh and not args.summary_only:
                out_fh.write(json.dumps({"type": "reachable",
                                          "cell": asdict(cell)},
                                         ensure_ascii=False) + "\n")
        else:
            unreachable_by_reason[u.reason] = unreachable_by_reason.get(u.reason, 0) + 1
            if out_fh and not args.summary_only:
                out_fh.write(json.dumps({"type": "unreachable",
                                          "cell": asdict(cell),
                                          "reason": u.reason,
                                          "evidence": u.evidence,
                                          "confidence": u.confidence},
                                         ensure_ascii=False) + "\n")

    if out_fh:
        out_fh.close()

    n_viewport_ext: int = gt["N_VIEWPORT_EXT"]
    summary: dict[str, Any] = {
        "total_cells": total,
        "expected_N_VIEWPORT_EXT": n_viewport_ext,
        "accounting_check": total == n_viewport_ext,
        "reachable": reachable,
        "unreachable_total": total - reachable,
        "unreachable_by_reason": unreachable_by_reason,
        "accounting_100pct": (reachable + (total - reachable)) == n_viewport_ext,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["accounting_check"] and summary["accounting_100pct"] else 1


if __name__ == "__main__":
    sys.exit(main())
