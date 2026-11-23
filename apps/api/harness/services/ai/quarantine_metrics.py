"""RAG quarantine metrics — backend portion (T279 dashboard UI env-blocked).

Aggregates `ai_outputs` rows into block-ratio and per-reason-code count
metrics that the AI Admin dashboard consumes. UI implementation lives
in `AIAdminDashboardPage.tsx` (env-blocked); this module is the data
shape + computation engine the routers expose to that page.

Reason-code taxonomy follows T262 (`ai_outputs.fail_closed_reason_code`
enum). Any code outside the closed set is bucketed as 'UNKNOWN' so a
schema mismatch surfaces in the dashboard rather than silently dropping.
"""

from __future__ import annotations

# Closed-set taxonomy per T262 (8 reason codes documented in BACKLOG).
KNOWN_REASON_CODES: frozenset[str] = frozenset({
    "NO_CITATION",
    "LOW_FAITHFULNESS",
    "PROMPT_INJECTION_DETECTED",
    "LLM07_LEAKAGE_REDACTED",
    "RATE_LIMIT_EXCEEDED",
    "MODERATION_BLOCK",
    "EMPTY_INPUT",
    "TIMEOUT",
})


def compute_metrics(
    ai_outputs_rows: list[dict[str, object]],
) -> dict[str, object]:
    """Aggregate one window of `ai_outputs` rows into dashboard metrics.

    Each row should carry at least:
      - `fail_closed`: bool — True iff the call was quarantined/blocked
      - `fail_closed_reason_code`: str — closed-set code (T262)
      - `agent`: str (optional) — for per-agent slicing
    Rows missing these fields are still counted toward `total_answers`
    but excluded from the by-reason-code bucket.

    Returns:
        total_answers: int
        blocked_count: int
        block_ratio: float (0.0 if total==0)
        by_reason_code: dict[str, int]
        by_agent: dict[str, dict[str, int]] — {agent: {blocked, total}}
        unknown_codes: list[str]
    """
    if not isinstance(ai_outputs_rows, list):
        raise TypeError("ai_outputs_rows must be a list")

    total = 0
    blocked = 0
    by_reason: dict[str, int] = {code: 0 for code in KNOWN_REASON_CODES}
    by_reason["UNKNOWN"] = 0
    by_agent: dict[str, dict[str, int]] = {}
    unknown_codes: list[str] = []

    for row in ai_outputs_rows:
        if not isinstance(row, dict):
            continue
        total += 1
        agent_raw = row.get("agent")
        agent = agent_raw if isinstance(agent_raw, str) else "_unknown"
        bucket = by_agent.setdefault(agent, {"blocked": 0, "total": 0})
        bucket["total"] += 1

        if row.get("fail_closed") is True:
            blocked += 1
            bucket["blocked"] += 1
            rc_raw = row.get("fail_closed_reason_code")
            rc = rc_raw if isinstance(rc_raw, str) else ""
            if rc in KNOWN_REASON_CODES:
                by_reason[rc] += 1
            else:
                by_reason["UNKNOWN"] += 1
                if rc and rc not in unknown_codes:
                    unknown_codes.append(rc)

    block_ratio = (blocked / total) if total else 0.0

    return {
        "total_answers": total,
        "blocked_count": blocked,
        "block_ratio": block_ratio,
        "by_reason_code": by_reason,
        "by_agent": by_agent,
        "unknown_codes": unknown_codes,
        "audit_action_code": "rag_quarantine_metrics_computed",
    }


def is_block_ratio_alarming(metrics: dict[str, object], threshold: float = 0.30) -> bool:
    """True if the block ratio exceeds the alarm threshold (default 30%).

    REG-06 §5 chaos-abort posture monitors block ratio: above 30% the
    `four_gate_failure_rate_high` audit row + auto-off recommendation
    should fire. This helper is the boolean test the monitoring rule uses.
    """
    ratio_raw = metrics.get("block_ratio")
    if not isinstance(ratio_raw, (int, float)):
        return False
    return float(ratio_raw) > threshold


def top_reason_codes(metrics: dict[str, object], k: int = 3) -> list[tuple[str, int]]:
    """Return the top-k non-zero reason codes by count, descending."""
    if k < 1:
        raise ValueError("k must be >= 1")
    by_reason_raw = metrics.get("by_reason_code")
    if not isinstance(by_reason_raw, dict):
        return []
    items = [(code, int(count)) for code, count in by_reason_raw.items() if int(count) > 0]
    items.sort(key=lambda t: (-t[1], t[0]))
    return items[:k]
