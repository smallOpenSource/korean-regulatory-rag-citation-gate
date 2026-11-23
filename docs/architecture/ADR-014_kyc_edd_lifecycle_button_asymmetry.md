# ADR-014 — KYC/EDD trigger lifecycle button asymmetry (reassess OPEN-only / complete OPEN+IN_PROGRESS)

- **Status**: Accepted (svc-viability-v3 B7, 2026-05-25)
- **Predecessor**: V029 (kyc_edd schema), V060 (lifecycle action codes)
- **Cycle**: svc-viability-v3

## Context

The backend repository SQL for the KYC/EDD trigger lifecycle is intentionally
asymmetric:

- `apps/api/harness/repositories/kyc_edd.py:53` —
  `UPDATE kyc_edd_triggers SET status='IN_PROGRESS', ... WHERE id=$1 AND status='OPEN'`
  → **reassess accepts OPEN only**.
- `apps/api/harness/repositories/kyc_edd.py:67` —
  `UPDATE kyc_edd_triggers SET status='CLOSED', ... WHERE id=$1 AND status IN ('OPEN','IN_PROGRESS')`
  → **complete accepts OPEN AND IN_PROGRESS**.

The pre-v3 UI gated **both** mutation buttons on `row.status === "OPEN"`,
which silently hid the `complete` button for IN_PROGRESS rows even though
the backend would have accepted the call. This was a user-visible bug:
once a trigger entered IN_PROGRESS it appeared terminal in the UI, with
no way for a compliance officer to close it without an out-of-band API
call or DB write.

`F16 canMutate intent` (deferred from svc-viability-v2 due to the
security skip) re-surfaced this in svc-viability-v3 as the per-button
gating gap.

## Decision

The UI's button visibility MUST mirror the SQL acceptance set
per-button, not a single conjunction:

| Button   | UI visibility condition                             |
|----------|-----------------------------------------------------|
| 재평가   | `canMutate && row.status === "OPEN"`                |
| 종결     | `canMutate && row.status in {"OPEN","IN_PROGRESS"}` |

`canMutate` itself stays the role-based gate
(`WRITE_ROLES = {"ADMIN","WM","BRANCH_MANAGER"}` per ADR-014's sibling
change in B6: backend SoT, PB removed).

## Consequences

- IN_PROGRESS rows now expose only the 종결 button; the 재평가 button
  is hidden because the backend would 404 with
  `"trigger not found or not in OPEN status"` (an honest UI signal).
- The button gating contract is testable: vitest
  `kyc-edd-page.test.tsx` MUST cover the IN_PROGRESS row case where
  재평가 is absent and 종결 is present.
- The asymmetry stays codified in two places: the SQL (authoritative)
  and the JSX (mirror). Drift detection MUST be exercised by a
  contract test (`tests/test_kyc_edd_lifecycle_contract.py`) that
  cross-references the JSX `row.status === "OPEN"` /
  `(row.status === "OPEN" || row.status === "IN_PROGRESS")` literals
  against the repository SQL WHERE clauses.

## Alternatives considered

- **Symmetric (both buttons require OPEN).** This was the pre-v3
  behavior. Rejected because it shadows a real lifecycle the backend
  supports (the IN_PROGRESS → CLOSED transition is the entire reason
  the V029 schema and V060 audit codes split `kyc_edd_reassessed`
  from `kyc_edd_completed`).
- **Backend tightened to OPEN-only for complete.** Rejected because
  compliance workflows legitimately need to close triggers that have
  already been moved to IN_PROGRESS (e.g. when an out-of-band
  investigation concludes), and the V029 schema already supports the
  IN_PROGRESS state with timestamps.

## Follow-ups

- vitest `apps/web/src/tests/kyc-edd-page.test.tsx` — assert the
  IN_PROGRESS row case (재평가 absent, 종결 present) and the OPEN row
  case (both present).
- pytest `tests/test_kyc_edd_lifecycle_contract.py` — cross-reference
  the JSX literals against the SQL WHERE clauses so any future drift
  fails CI.
