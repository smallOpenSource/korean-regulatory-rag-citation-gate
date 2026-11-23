"""Wave-Audit-Defect-Fix B4 — docs/api/API-01_contracts.yaml ↔ email router parity.

Plan §6 line 330: YAML role drift 정합. The submit/approve/reject endpoints
all go through ``require_email_staff`` at routers/email.py:44-47 which
enforces PB/WM only. The four-eye rule (a reviewer cannot approve their
own draft) is enforced via author equality at line 348-ish, not via a
role split — the legacy "ADMIN/WM role required" text on approve/reject
in the YAML was stale drift.

Acceptance gate (binary): schemathesis role mismatch 0건. This structural
test asserts the YAML and code agree on the {PB, WM} role set.
"""

from __future__ import annotations

import re
from pathlib import Path


def test_require_email_staff_enforces_pb_wm() -> None:
    body = (Path(__file__).resolve().parents[1] / "apps/api/harness/api/routers/email.py").read_text(encoding="utf-8")
    match = re.search(
        r"def require_email_staff\([^)]*\)[^{]*?role_code not in \{([^}]+)\}",
        body,
        re.DOTALL,
    )
    assert match, "require_email_staff role gate must remain inline-readable"
    roles_text = match.group(1)
    role_set = {r.strip().strip('"') for r in roles_text.split(",") if r.strip()}
    assert role_set == {"PB", "WM"}, (
        f"require_email_staff must gate on {{PB, WM}} only; got {role_set}"
    )


def test_yaml_email_endpoints_describe_pb_wm_not_admin_wm() -> None:
    body = (Path(__file__).resolve().parents[1] / "docs/api/API-01_contracts.yaml").read_text(encoding="utf-8")
    # Locate the 3 endpoint blocks
    for endpoint in (
        "/email-drafts/{draft_id}/submit:",
        "/email-drafts/{draft_id}/approve:",
        "/email-drafts/{draft_id}/reject:",
    ):
        idx = body.find(endpoint)
        assert idx != -1, f"YAML must declare {endpoint}"
        block = body[idx : idx + 400]
        assert "PB/WM role required" in block, (
            f"{endpoint} block must describe PB/WM role required (code parity)"
        )
        assert "ADMIN/WM role required" not in block, (
            f"{endpoint} must no longer claim ADMIN/WM role required — that was "
            "YAML drift; the code uses PB/WM"
        )


def test_yaml_documents_four_eye_rule_on_approve_reject() -> None:
    body = (Path(__file__).resolve().parents[1] / "docs/api/API-01_contracts.yaml").read_text(encoding="utf-8")
    # The four-eye rule (author cannot approve own draft) is enforced at the
    # row level, not via role. Doc must hint at it so consumers don't expect
    # role-based separation.
    for endpoint in ("approve", "reject"):
        idx = body.find(f"/email-drafts/{{draft_id}}/{endpoint}:")
        block = body[idx : idx + 400]
        assert "four-eye" in block, (
            f"{endpoint} doc must mention four-eye author-different rule "
            "(enforced via author equality, not role split)"
        )


def test_b4_comment_anchors_the_fix() -> None:
    body = (Path(__file__).resolve().parents[1] / "docs/api/API-01_contracts.yaml").read_text(encoding="utf-8")
    assert "Wave-Audit-Defect-Fix B4" in body, (
        "YAML must carry an inline B4 marker so the alignment intent is "
        "preserved against future drift"
    )
