"""AI output feedback (T269) — backend portion (👍/👎 UI is env-blocked).

Owns the record schema, validation, and aggregation logic for the
`ai_output_feedback` table that V043 will create. UI calls this service
to record a thumbs-up / thumbs-down event on an AI output; the AI Admin
dashboard (T279) queries `aggregate_by_agent` to render the per-agent
feedback distribution.
"""

from __future__ import annotations

from datetime import UTC, datetime

VALID_POLARITIES: frozenset[str] = frozenset({"positive", "negative"})

# Closed-set reason codes the UI surfaces; free-text comments live in a
# separate `comment` field (PII-redacted by upstream pii_masking).
VALID_REASON_CODES: frozenset[str] = frozenset({
    "ACCURATE",
    "WELL_CITED",
    "TIMELY",
    "RELEVANT_TO_CONTEXT",
    "HALLUCINATED",
    "MISSING_CITATION",
    "OUT_OF_DATE",
    "OFF_TOPIC",
    "INSENSITIVE_TONE",
    "REGULATORY_RISK",
})


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_feedback(
    *,
    ai_output_id: str,
    employee_id: str,
    polarity: str,
    reason_code: str = "",
    comment: str = "",
    customer_id: str = "",
    now: str | None = None,
) -> dict[str, object]:
    """Compose one feedback row.

    Validation:
      - polarity must be 'positive' or 'negative'
      - reason_code (if given) must be in VALID_REASON_CODES
      - ai_output_id + employee_id required (PB/WM who clicked the button)
    """
    if not ai_output_id or not employee_id:
        raise ValueError("ai_output_id and employee_id required")
    if polarity not in VALID_POLARITIES:
        raise ValueError(f"polarity must be positive|negative, got {polarity!r}")
    if reason_code and reason_code not in VALID_REASON_CODES:
        raise ValueError(f"unknown reason_code: {reason_code!r}")
    return {
        "ai_output_id": ai_output_id,
        "employee_id": employee_id,
        "customer_id": customer_id,
        "polarity": polarity,
        "reason_code": reason_code,
        "comment": comment,
        "recorded_at": now or _utc_now_iso(),
        "audit_action_code": "ai_output_feedback_recorded",
    }


def aggregate_by_agent(
    records: list[dict[str, object]],
    agent_lookup: dict[str, str],
) -> dict[str, dict[str, object]]:
    """Aggregate feedback per agent.

    `agent_lookup` maps ai_output_id → agent_name. (In production this
    comes from a JOIN against ai_outputs; isolated here so the unit
    layer doesn't need a DB connection.)

    Returns:
        { agent_name: { positive: int, negative: int, total: int,
                       positive_ratio: float, reasons: dict[str, int] } }
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    if not isinstance(agent_lookup, dict):
        raise TypeError("agent_lookup must be a dict")

    agg: dict[str, dict[str, object]] = {}
    for row in records:
        aid_raw = row.get("ai_output_id")
        if not isinstance(aid_raw, str):
            continue
        agent = agent_lookup.get(aid_raw)
        if agent is None:
            continue
        bucket = agg.setdefault(
            agent,
            {"positive": 0, "negative": 0, "total": 0, "reasons": {}},
        )
        pol = row.get("polarity")
        if pol == "positive":
            bucket["positive"] = int(bucket["positive"]) + 1  # type: ignore[arg-type]
        elif pol == "negative":
            bucket["negative"] = int(bucket["negative"]) + 1  # type: ignore[arg-type]
        bucket["total"] = int(bucket["total"]) + 1  # type: ignore[arg-type]
        rc = row.get("reason_code")
        if isinstance(rc, str) and rc:
            reasons = bucket["reasons"]
            if isinstance(reasons, dict):
                reasons[rc] = int(reasons.get(rc, 0)) + 1  # type: ignore[arg-type]

    for agent, bucket in agg.items():
        pos = int(bucket["positive"])  # type: ignore[arg-type]
        total = int(bucket["total"])  # type: ignore[arg-type]
        bucket["positive_ratio"] = (pos / total) if total else 0.0
    return agg


def is_feedback_actionable(record: dict[str, object]) -> bool:
    """Heuristic: a negative-polarity feedback with a regulatory or
    citation-related reason_code should be escalated for review."""
    if record.get("polarity") != "negative":
        return False
    rc = record.get("reason_code")
    return rc in {"REGULATORY_RISK", "HALLUCINATED", "MISSING_CITATION", "INSENSITIVE_TONE"}
