"""Azure Content Safety toggle hooks (T273 Prompt Shields + T274 Groundedness).

REG-04 §6 expects two Azure Content Safety advanced features to be
configurable behind explicit feature flags (default OFF):

  T273 — Prompt Shields: catches indirect prompt-injection patterns in
         user prompts and tool/document context before LLM submission.
  T274 — Groundedness Detection: flags LLM completions whose factual
         claims are not supported by the supplied grounding context.

Both are EXPENSIVE per-call probes and should be opt-in at the PoC
boundary (env + DB feature_flags). This module owns the toggle state,
the audit-action-code emission on flip, and the policy guard the
upstream caller invokes before each call.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

# ─── Env-var names (single source) ────────────────────────────────────────────

ENV_PROMPT_SHIELDS = "AZURE_CONTENT_SAFETY_PROMPT_SHIELDS_ENABLED"
ENV_GROUNDEDNESS = "AZURE_CONTENT_SAFETY_GROUNDEDNESS_ENABLED"


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_truthy(name: str) -> bool:
    """True iff env var is set to a canonical truthy value."""
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}


# ─── Public API ───────────────────────────────────────────────────────────────


def is_prompt_shields_enabled(env: dict[str, str] | None = None) -> bool:
    """Return True iff Prompt Shields is opt-in via env. Default OFF.

    `env` override lets callers and tests inject deterministic state
    without touching `os.environ`.
    """
    if env is not None:
        value = env.get(ENV_PROMPT_SHIELDS, "").strip().lower()
        return value in {"1", "true", "yes", "on", "enabled"}
    return _env_truthy(ENV_PROMPT_SHIELDS)


def is_groundedness_enabled(env: dict[str, str] | None = None) -> bool:
    """Return True iff Groundedness Detection is opt-in via env. Default OFF."""
    if env is not None:
        value = env.get(ENV_GROUNDEDNESS, "").strip().lower()
        return value in {"1", "true", "yes", "on", "enabled"}
    return _env_truthy(ENV_GROUNDEDNESS)


def evaluate_toggles(env: dict[str, str] | None = None) -> dict[str, object]:
    """Snapshot both toggles + emit a single decision record.

    Returns:
        prompt_shields_enabled: bool
        groundedness_enabled: bool
        active_count: 0|1|2
        evaluated_at: ISO 8601 UTC
        audit_action_code: 'content_safety_toggles_evaluated'
    """
    ps = is_prompt_shields_enabled(env)
    gd = is_groundedness_enabled(env)
    return {
        "prompt_shields_enabled": ps,
        "groundedness_enabled": gd,
        "active_count": int(ps) + int(gd),
        "evaluated_at": _utc_now_iso(),
        "audit_action_code": "content_safety_toggles_evaluated",
    }


def build_toggle_change_audit(
    *,
    toggle: str,
    previous: bool,
    new: bool,
    actor_id: str,
) -> dict[str, object]:
    """Build an audit row for a toggle flip operation.

    `toggle` must be 'prompt_shields' or 'groundedness'. Used by an
    admin endpoint that updates the DB feature_flags row so that
    audit reviewers can trace who flipped what when.
    """
    if toggle not in {"prompt_shields", "groundedness"}:
        raise ValueError(f"unknown toggle: {toggle!r}")
    if not isinstance(previous, bool) or not isinstance(new, bool):
        raise TypeError("previous and new must be booleans")
    if not actor_id:
        raise ValueError("actor_id required")
    if previous == new:
        raise ValueError("no-op toggle change is not auditable")
    direction = "enabled" if new else "disabled"
    code = f"content_safety_{toggle}_{direction}"
    return {
        "toggle": toggle,
        "previous": previous,
        "new": new,
        "actor_id": actor_id,
        "changed_at": _utc_now_iso(),
        "audit_action_code": code,
    }


def guard_call(
    *,
    feature: str,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Return {allowed: bool, reason: str} for a single Azure CS feature call.

    Callers about to invoke the Prompt Shields / Groundedness API must
    consult this guard first so that disabled features don't accrue
    cost and that the closed-set reason code lands in audit_logs.
    """
    if feature == "prompt_shields":
        enabled = is_prompt_shields_enabled(env)
    elif feature == "groundedness":
        enabled = is_groundedness_enabled(env)
    else:
        raise ValueError(f"unknown feature: {feature!r}")
    if enabled:
        return {
            "allowed": True,
            "feature": feature,
            "reason": "FEATURE_TOGGLE_ENABLED",
            "audit_action_code": f"content_safety_{feature}_invoked",
        }
    return {
        "allowed": False,
        "feature": feature,
        "reason": "FEATURE_TOGGLE_DISABLED",
        "audit_action_code": f"content_safety_{feature}_skipped_disabled",
    }
