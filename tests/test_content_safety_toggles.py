"""Stage 5 T273 + T274 — Azure Content Safety toggle hooks."""

from __future__ import annotations

import pytest

from apps.api.harness.services.ai.content_safety_toggles import (
    ENV_GROUNDEDNESS,
    ENV_PROMPT_SHIELDS,
    build_toggle_change_audit,
    evaluate_toggles,
    guard_call,
    is_groundedness_enabled,
    is_prompt_shields_enabled,
)


def test_default_prompt_shields_off():
    """T273 default OFF per BACKLOG."""
    assert is_prompt_shields_enabled(env={}) is False


def test_default_groundedness_off():
    """T274 default OFF per BACKLOG."""
    assert is_groundedness_enabled(env={}) is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "enabled"])
def test_prompt_shields_truthy_variants_enable(value):
    assert is_prompt_shields_enabled(env={ENV_PROMPT_SHIELDS: value}) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "disabled", "", "garbage"])
def test_prompt_shields_falsy_variants_disable(value):
    assert is_prompt_shields_enabled(env={ENV_PROMPT_SHIELDS: value}) is False


def test_evaluate_toggles_both_off():
    snap = evaluate_toggles(env={})
    assert snap["prompt_shields_enabled"] is False
    assert snap["groundedness_enabled"] is False
    assert snap["active_count"] == 0
    assert snap["audit_action_code"] == "content_safety_toggles_evaluated"
    assert snap["evaluated_at"].endswith("Z")


def test_evaluate_toggles_both_on():
    snap = evaluate_toggles(env={
        ENV_PROMPT_SHIELDS: "true",
        ENV_GROUNDEDNESS: "1",
    })
    assert snap["prompt_shields_enabled"] is True
    assert snap["groundedness_enabled"] is True
    assert snap["active_count"] == 2


def test_evaluate_toggles_one_each():
    snap = evaluate_toggles(env={ENV_PROMPT_SHIELDS: "true"})
    assert snap["active_count"] == 1


def test_build_toggle_change_audit_enable():
    audit = build_toggle_change_audit(
        toggle="prompt_shields",
        previous=False,
        new=True,
        actor_id="admin-1",
    )
    assert audit["audit_action_code"] == "content_safety_prompt_shields_enabled"
    assert audit["previous"] is False
    assert audit["new"] is True
    assert audit["changed_at"].endswith("Z")


def test_build_toggle_change_audit_disable():
    audit = build_toggle_change_audit(
        toggle="groundedness",
        previous=True,
        new=False,
        actor_id="admin-1",
    )
    assert audit["audit_action_code"] == "content_safety_groundedness_disabled"


def test_build_toggle_change_audit_rejects_unknown_toggle():
    with pytest.raises(ValueError):
        build_toggle_change_audit(
            toggle="rogue_filter",
            previous=False,
            new=True,
            actor_id="admin-1",
        )


def test_build_toggle_change_audit_rejects_noop():
    with pytest.raises(ValueError):
        build_toggle_change_audit(
            toggle="prompt_shields",
            previous=True,
            new=True,
            actor_id="admin-1",
        )


def test_build_toggle_change_audit_requires_actor():
    with pytest.raises(ValueError):
        build_toggle_change_audit(
            toggle="prompt_shields",
            previous=False,
            new=True,
            actor_id="",
        )


def test_build_toggle_change_audit_type_safety():
    with pytest.raises(TypeError):
        build_toggle_change_audit(
            toggle="prompt_shields",
            previous=0,  # type: ignore[arg-type]
            new=True,
            actor_id="admin-1",
        )


def test_guard_call_allowed_when_enabled():
    g = guard_call(feature="prompt_shields", env={ENV_PROMPT_SHIELDS: "true"})
    assert g["allowed"] is True
    assert g["reason"] == "FEATURE_TOGGLE_ENABLED"
    assert g["audit_action_code"] == "content_safety_prompt_shields_invoked"


def test_guard_call_blocked_when_disabled():
    g = guard_call(feature="prompt_shields", env={})
    assert g["allowed"] is False
    assert g["reason"] == "FEATURE_TOGGLE_DISABLED"
    assert g["audit_action_code"] == "content_safety_prompt_shields_skipped_disabled"


def test_guard_call_groundedness_blocked_default():
    g = guard_call(feature="groundedness", env={})
    assert g["allowed"] is False
    assert g["audit_action_code"] == "content_safety_groundedness_skipped_disabled"


def test_guard_call_rejects_unknown_feature():
    with pytest.raises(ValueError):
        guard_call(feature="unknown_feature", env={})
