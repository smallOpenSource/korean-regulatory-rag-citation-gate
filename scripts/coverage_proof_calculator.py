#!/usr/bin/env python3
"""v8 coverage_proof_calculator — PRD §10.1 + DELTA-3/C3 + DELTA-N1.

External SoT only — NOT discovered_edges 자기참조. external_ground_truth_total
은 v8-ground-truth.yaml의 N_VIEWPORT_EXT (immutable cycle-1-baseline) 에서만 read.

Gate: ratio == 1.0 (100% accounting). 95% threshold 거부 (DELTA-3 strict).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def calculate_coverage(
    visited_cells: list[str],
    unreachable_manifest: list[str],
    ground_truth_yaml_path: str | Path,
) -> dict[str, object]:
    """Compute coverage ratio from external SoT only.

    Args:
        visited_cells: List of state_hash strings emitted by the BFS visitor.
        unreachable_manifest: List of cell IDs marked unreachable (from
            v8-unreachable-manifest.yaml).
        ground_truth_yaml_path: Path to v8-ground-truth.yaml (LOCKED baseline).

    Returns:
        dict with total / visited / unreachable_marked / accounted / ratio /
        gate_pass keys.
    """
    import yaml  # local import keeps the module importable without PyYAML.

    with open(ground_truth_yaml_path, encoding="utf-8") as f:
        gt = yaml.safe_load(f)
    total = gt["N_VIEWPORT_EXT"]

    visited_set = set(visited_cells)
    unreachable_set = set(unreachable_manifest)
    accounted = len(visited_set) + len(unreachable_set)
    ratio = accounted / total if total else 0.0
    # Strict equality — DELTA-3 forbids any tolerance threshold.
    gate_pass = accounted == total

    return {
        "total": total,
        "visited": len(visited_set),
        "unreachable_marked": len(unreachable_set),
        "accounted": accounted,
        "ratio": ratio,
        "gate_pass": gate_pass,
    }


def _self_test(ground_truth_path: str | Path) -> int:
    """4-case self-test invoked via --self-test."""
    import yaml

    with open(ground_truth_path, encoding="utf-8") as f:
        gt = yaml.safe_load(f)
    total = gt["N_VIEWPORT_EXT"]

    # Build dummy cell IDs as "cell-<index>".
    all_cells = [f"cell-{i}" for i in range(total)]

    cases: list[tuple[str, list[str], list[str], bool]] = [
        ("Test 1: 100% visited, 0% unreachable", all_cells, [], True),
        ("Test 2: 50% visited, 50% unreachable", all_cells[: total // 2], all_cells[total // 2 :], True),
        (
            "Test 3: 97.5% visited, 0% unreachable (must FAIL — no 95% threshold)",
            all_cells[: int(total * 0.975)],
            [],
            False,
        ),
        (
            "Test 4: dedupe via set — duplicates ignored",
            all_cells + all_cells[:100],
            [],
            True,
        ),
    ]

    all_pass = True
    for label, visited, unreach, expected_pass in cases:
        result = calculate_coverage(visited, unreach, ground_truth_path)
        actual = bool(result["gate_pass"])
        status = "PASS" if actual == expected_pass else "FAIL"
        if actual != expected_pass:
            all_pass = False
        print(
            f"  {status}  {label}  → ratio={result['ratio']:.4f} accounted={result['accounted']}/{result['total']} gate={actual}"
        )

    return 0 if all_pass else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="v8 coverage proof calculator")
    parser.add_argument(
        "--ground-truth",
        default=".omc/state/v8-ground-truth.yaml",
        help="Path to v8-ground-truth.yaml (locked baseline)",
    )
    parser.add_argument(
        "--visited",
        help="Path to JSON file containing list of state_hash strings (visited cells)",
    )
    parser.add_argument(
        "--unreachable",
        help="Path to JSON file containing list of cell IDs (unreachable manifest)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run 4-case self-test against ground truth and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test(args.ground_truth)

    if not args.visited or not args.unreachable:
        parser.error("--visited and --unreachable required unless --self-test")

    with open(args.visited, encoding="utf-8") as f:
        visited = json.load(f)
    with open(args.unreachable, encoding="utf-8") as f:
        unreachable = json.load(f)

    result = calculate_coverage(visited, unreachable, args.ground_truth)
    print(json.dumps(result, indent=2))
    return 0 if result["gate_pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
