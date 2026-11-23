#!/usr/bin/env python3
"""ADR-007 §2 validator: 금융 AI 7대 원칙 self-assessment report (T321).

Aggregates evidence from the 5-wave delivery and emits a 7-principles × 7-agent
matrix to ``.omc/specs/`` (default) or a caller-specified path. Exit codes follow
the ADR-007 contract:

    0 — all 7 principles meet minimum threshold
    2 — one or more principles fail (per-principle floor breached)
    3 — config error (missing inputs)

Output JSON structure (also rendered as Markdown when ``--also-markdown``):

    {
      "verified_at": "<ISO-8601 UTC>",
      "status": "passed|failed",
      "passed": true,
      "principles": {"<id>": {"score": 0.0-1.0, "agents": {"<agent>": {...}}}},
      "evidence_paths": ["<path>", ...]
    }

The seven principles are sourced from FSC AI 가이드라인 + KISA AI 윤리:

    P1_safety          — fail-closed coverage on 7 agents
    P2_accountability  — every ai_output row carries audit chain + employee_final_approval
    P3_transparency    — Model Cards published for 7 agents; AI metadata 4-tuple footer
    P4_fairness        — synthetic-only data + risk-grade enforcement (no real PII bias)
    P5_privacy         — PII redaction + pseudonym_label + 신용정보법 §40-2 metadata
    P6_security        — RBAC + WS ticket flow + audit append-only + rate ceilings
    P7_robustness      — dual-LLM quarantine + injection_detector + output_sanitizer

This script performs STATIC checks only — file existence anchors only. Runtime
metrics (faithfulness/fail-closed rate/etc.) are aggregated by
``aggregate_principle_runtime_metrics.py``. Composite verification:
``verify_total_product_readiness.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENTS = (
    "house_view_generation",
    "consultation_briefing",
    "nba_script",
    "email_draft",
    "rag_qa",
    "compliance_check",
    "portfolio_analysis",
)
PRINCIPLES = (
    "P1_safety",
    "P2_accountability",
    "P3_transparency",
    "P4_fairness",
    "P5_privacy",
    "P6_security",
    "P7_robustness",
)

# Per-principle floor — a single agent below this score causes the principle to fail.
PRINCIPLE_FLOOR = 0.6


def _score_agent(principle: str, agent: str) -> tuple[float, list[str]]:
    """Return (score, evidence_paths) for one principle × agent pair."""
    evidence: list[str] = []
    base = 0.5

    if principle == "P1_safety":
        card = PROJECT_ROOT / "docs" / "ai" / "model_cards" / f"{agent}.md"
        if card.exists():
            base += 0.3
            evidence.append(str(card.relative_to(PROJECT_ROOT)))
        # fail-closed reason codes in router
        router = PROJECT_ROOT / "apps" / "api" / "harness" / "api" / "routers" / "ai.py"
        if router.exists() and "fail_closed_reason_code" in router.read_text():
            base += 0.2
            evidence.append(str(router.relative_to(PROJECT_ROOT)))
    elif principle == "P2_accountability":
        v039 = PROJECT_ROOT / "db" / "migrations" / "V039__t201_t231_t276_audit_codes_and_employee_final_approval.sql"
        if v039.exists():
            base += 0.4
            evidence.append(str(v039.relative_to(PROJECT_ROOT)))
        adr006 = PROJECT_ROOT / "docs" / "architecture" / "ADR-006_audit_append_only_trigger.md"
        if adr006.exists():
            base += 0.1
            evidence.append(str(adr006.relative_to(PROJECT_ROOT)))
    elif principle == "P3_transparency":
        card = PROJECT_ROOT / "docs" / "ai" / "model_cards" / f"{agent}.md"
        if card.exists():
            base += 0.5
            evidence.append(str(card.relative_to(PROJECT_ROOT)))
    elif principle == "P4_fairness":
        v027 = PROJECT_ROOT / "db" / "migrations" / "V027__consents_synthetic.sql"
        v037 = PROJECT_ROOT / "db" / "migrations" / "V037__synthetic_customer_no_check.sql"
        if v027.exists():
            base += 0.25
            evidence.append(str(v027.relative_to(PROJECT_ROOT)))
        if v037.exists():
            base += 0.25
            evidence.append(str(v037.relative_to(PROJECT_ROOT)))
    elif principle == "P5_privacy":
        redact = PROJECT_ROOT / "apps" / "api" / "harness" / "core" / "redaction.py"
        v033 = PROJECT_ROOT / "db" / "migrations" / "V033__credit_info_metadata.sql"
        if redact.exists():
            base += 0.25
            evidence.append(str(redact.relative_to(PROJECT_ROOT)))
        if v033.exists():
            base += 0.25
            evidence.append(str(v033.relative_to(PROJECT_ROOT)))
    elif principle == "P6_security":
        adr001 = PROJECT_ROOT / "docs" / "architecture" / "ADR-001_websocket_delivery_contract.md"
        token_meter = PROJECT_ROOT / "apps" / "api" / "harness" / "services" / "ai" / "token_meter.py"
        if adr001.exists():
            base += 0.25
            evidence.append(str(adr001.relative_to(PROJECT_ROOT)))
        if token_meter.exists():
            base += 0.25
            evidence.append(str(token_meter.relative_to(PROJECT_ROOT)))
    elif principle == "P7_robustness":
        adr005 = PROJECT_ROOT / "docs" / "architecture" / "ADR-005_dual_llm_quarantine.md"
        injection = PROJECT_ROOT / "apps" / "api" / "harness" / "services" / "ai" / "injection_detector.py"
        sanitizer = PROJECT_ROOT / "apps" / "api" / "harness" / "services" / "ai" / "output_sanitizer.py"
        for path in (adr005, injection, sanitizer):
            if path.exists():
                base += 0.166
                evidence.append(str(path.relative_to(PROJECT_ROOT)))

    return min(base, 1.0), evidence


def build_report(out_dir: Path) -> tuple[dict[str, object], int]:
    verified_at = datetime.now(tz=timezone.utc).isoformat()
    principles_report: dict[str, dict[str, object]] = {}
    all_evidence: set[str] = set()
    any_failed = False

    for principle in PRINCIPLES:
        agent_scores: dict[str, dict[str, object]] = {}
        principle_min = 1.0
        for agent in AGENTS:
            score, ev = _score_agent(principle, agent)
            agent_scores[agent] = {"score": round(score, 3), "evidence": ev}
            principle_min = min(principle_min, score)
            all_evidence.update(ev)
        passed = principle_min >= PRINCIPLE_FLOOR
        if not passed:
            any_failed = True
        principles_report[principle] = {
            "score": round(principle_min, 3),
            "passed": passed,
            "floor": PRINCIPLE_FLOOR,
            "agents": agent_scores,
        }

    report = {
        "verified_at": verified_at,
        "status": "failed" if any_failed else "passed",
        "passed": not any_failed,
        "principles": principles_report,
        "evidence_paths": sorted(all_evidence),
    }
    return report, (2 if any_failed else 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / ".omc" / "specs" / f"seven-principles-report-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    )
    parser.add_argument("--also-markdown", action="store_true")
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    report, exit_code = build_report(args.out.parent)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.also_markdown:
        md_lines = ["# 금융 AI 7대 원칙 self-assessment", "", f"verified_at: {report['verified_at']}", f"status: {report['status']}", ""]
        for pid, p in report["principles"].items():
            md_lines.append(f"## {pid} — score={p['score']} passed={p['passed']}")
            for agent, a in p["agents"].items():
                md_lines.append(f"- {agent}: {a['score']}")
            md_lines.append("")
        args.out.with_suffix(".md").write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps({"status": report["status"], "passed": report["passed"], "out": str(args.out)}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
