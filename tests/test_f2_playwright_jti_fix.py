"""Wave-Audit-Defect-Fix F2 — Playwright per-test fresh login + JTI rotation fix.

Plan §6 line 478 acceptance: per-test fresh login fixture + 700ms wait +
login-retry per [[bfs-auth-race-window]]. Target: Playwright re-run outcome
match ≥ 80% (현 17%).

Runtime measurement of "≥ 80% match" requires a live Playwright run against
the dashboard; the structural assertions here lock the spec contract so the
shared-storageState regression cannot silently come back.
"""

from __future__ import annotations

from pathlib import Path


def test_spec_imports_role_emails_and_password() -> None:
    body = (Path(__file__).resolve().parents[1] / "tests/audit-e2e/all-pages-by-role.spec.ts").read_text(encoding="utf-8")
    assert "ROLE_EMAILS" in body, (
        "spec must define ROLE_EMAILS so freshLogin can drive the form"
    )
    assert "synthetic.pb1@example.invalid" in body
    assert "synthetic.wm1@example.invalid" in body
    assert "synthetic.admin@example.invalid" in body
    assert "synthetic.audit@example.invalid" in body
    assert 'process.env.WMAH_E2E_PASSWORD' in body, (
        "password must be overridable via env; default is preserved as fallback"
    )


def test_spec_defines_freshLogin_helper() -> None:
    body = (Path(__file__).resolve().parents[1] / "tests/audit-e2e/all-pages-by-role.spec.ts").read_text(encoding="utf-8")
    assert "async function freshLogin(page: Page, role: RoleCode)" in body, (
        "freshLogin helper signature must be present"
    )
    # 700ms hard wait per [[bfs-auth-race-window]] memory rule
    assert "page.waitForTimeout(700)" in body, (
        "post-login settle wait must be 700ms (Playwright networkidle is not enough)"
    )


def test_spec_runs_freshLogin_in_beforeEach() -> None:
    body = (Path(__file__).resolve().parents[1] / "tests/audit-e2e/all-pages-by-role.spec.ts").read_text(encoding="utf-8")
    assert "test.beforeEach(async ({ page })" in body, (
        "fresh login must be in beforeEach so EVERY test in the role describe "
        "gets a brand-new login (JTI rotation collision fix)"
    )
    assert "await freshLogin(page, role)" in body


def test_spec_storage_state_is_now_fallback_only() -> None:
    body = (Path(__file__).resolve().parents[1] / "tests/audit-e2e/all-pages-by-role.spec.ts").read_text(encoding="utf-8")
    # storageState must be opt-in via env, not the default
    assert 'process.env.WMAH_E2E_USE_STORAGE_STATE === "1"' in body, (
        "WMAH_E2E_USE_STORAGE_STATE env flag must be the only way to revert "
        "to the legacy shared-storageState path (for diagnostic comparison)"
    )
    # The unconditional test.use({ storageState }) regression must be gone
    assert "test.use(stateExists ? { storageState: statePath } : {});" not in body, (
        "legacy unconditional storageState use must be replaced with the "
        "useStorageState-guarded variant"
    )
