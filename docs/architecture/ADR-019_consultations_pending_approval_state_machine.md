# ADR-019 — `consultations` PENDING_APPROVAL State Machine + 4-Eye Preventive Gate

- **Status**: Accepted (svc-viability-v4 W4, 2026-05-25). Implemented via V076 (V062 mirror DROP/ADD 8-status + `consultation_submitted_for_approval` action_code INSERT) + router branches at `routers/consultations.py:update_consultation` (W2 commit) implementing the preventive `four_eyes_violation_blocked` + Input-6 dual-emit SKIP rule (cardinality contract: exactly 1 preventive row, zero detective row). V005:15-17 anonymous CHECK `consultations_complete_checks` preserved (verified at W0b via `\d+ consultations`).
- **Predecessor**: svc-viability-v3 closure handoff §4 follow-up row 4 — v3 shipped `same_actor_mutation_blocked` as an **audit-only detective control**. v4 introduces the **preventive** gate by extending the consultation state machine with `PENDING_APPROVAL`.
- **Cycle**: svc-viability-v4 (ralplan iter-2 APPROVE)
- **Plan SoT**: `<repo-root>/.omc/plans/ralplan-wmah-service-viability-v4.md` §4 I4 + §11.

---

## Context

The v3 detective at `routers/consultations.py:103-117` emits `same_actor_mutation_blocked` whenever the PATCH actor matches the consultation creator. The HTTP response stays `200` and the mutation goes through — the audit row is informational only. Regulatory expectation is **preventive**: the creator must not be able to mark their own consultation `COMPLETED` (four-eye rule).

Implementing a preventive gate requires an intermediate state between `SAVED` and `COMPLETED` so that the gating point ("am I about to approve my own work?") can be identified deterministically. The intermediate state is `PENDING_APPROVAL`. The starting domain for the constraint is **8-status** (V062 7-status + `PENDING_APPROVAL`), not the historical V005 3-status.

## Decision

### V076 — V062 mirror DROP/ADD with `PENDING_APPROVAL`

```sql
/* sql_id: v076_consultations_pending_approval */
-- Pre-V076 domain (V062 applied):
-- {DRAFT, SAVED, COMPLETED, CANCELLED, REJECTED, DISMISSED, EXPIRED} (7 codes)
-- V076 adds PENDING_APPROVAL for the 4-eye preventive gate.
-- Strictly broader extension — every existing row remains valid.

ALTER TABLE consultations
    DROP CONSTRAINT IF EXISTS consultations_status_code_check;

/* sql_id: v076_add_extended_consultation_status_check */
ALTER TABLE consultations
    ADD CONSTRAINT consultations_status_code_check
    CHECK (status_code IN (
        'DRAFT', 'SAVED', 'PENDING_APPROVAL', 'COMPLETED',
        'CANCELLED', 'REJECTED', 'DISMISSED', 'EXPIRED'
    ));
```

Mirror of V062 ALTER pattern. Target is `consultations_status_code_check` only. The anonymous CHECK `consultations_complete_checks` (V005:15-17, `status_code <> 'COMPLETED' OR (suitability_checked IS TRUE AND explanation_checked IS TRUE)`) is **preserved** and is verified after migration via `\d+ consultations` (Input-2 mandate).

### State machine (text diagram)

```
        ┌─────────┐
        │  DRAFT  │
        └────┬────┘
             │ PATCH status_code=SAVED
             ▼
        ┌─────────┐
        │  SAVED  │─────────────────────────────┐
        └────┬────┘                             │
             │ PATCH status_code=                │ PATCH status_code=COMPLETED (legacy direct path)
             │ PENDING_APPROVAL                  │ 4-gate check + 200
             ▼                                   │
   ┌────────────────────┐                        │
   │  PENDING_APPROVAL  │                        │
   └────┬───────────┬───┘                        │
        │           │ PATCH status_code=COMPLETED│
        │           │   actor != creator         │
        │           │   → 200 + audit            │
        │           ▼                            │
        │     ┌───────────┐ ◀───────────────────┘
        │     │ COMPLETED │
        │     └───────────┘
        │ PATCH status_code=COMPLETED, actor == creator
        │   → 403 + four_eyes_violation_blocked
        ▼
   (request rejected, row stays PENDING_APPROVAL)
```

Transitions out of `PENDING_APPROVAL` to `CANCELLED`, `REJECTED`, `DISMISSED`, `EXPIRED` follow the existing handlers and are not 4-eye-gated.

### Router emit semantics (Input-5 transaction wrap + Input-6 SKIP rule)

```python
# routers/consultations.py update_consultation
async with get_pool(request).acquire() as connection:
    existing = await consultation_repo.get_consultation_for_actor(...)
    if existing is None:
        raise HTTPException(404, ...)

    # Input-6 dual-emit SKIP rule:
    #   PENDING_APPROVAL → COMPLETED + same-actor = preventive 4-eye only.
    #   Do NOT also emit the detective same_actor_mutation_blocked on this path.
    if (
        existing["status_code"] == "PENDING_APPROVAL"
        and payload.get("status_code") == "COMPLETED"
        and same_actor(actor.employee_id, existing["employee_id"])
    ):
        async with connection.transaction():
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="four_eyes_violation_blocked",
                resource_type="consultation",
                resource_id=consultation_id_text,
                detail={
                    "creator_id": str(existing["employee_id"]),
                    "approver_id": str(actor.employee_id),
                    "preventive_path": "PENDING_APPROVAL → COMPLETED",
                },
                **request_audit_context(request),
            )
            raise HTTPException(
                403,
                "consultation completion requires a different approver (four-eye rule)",
            )
        # SKIP detective same_actor_mutation_blocked in this preventive path

    elif same_actor(actor.employee_id, existing["employee_id"]):
        # v3 carry-over detective, NOT transactional (preserved by Input-5 split).
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="same_actor_mutation_blocked",
            resource_type="consultation",
            resource_id=str(existing["id"]),
            detail={"original_creator_id": str(existing["employee_id"])},
            **request_audit_context(request),
        )

    # New transition: DRAFT/SAVED → PENDING_APPROVAL emits the submission event.
    if (
        existing["status_code"] in ("DRAFT", "SAVED")
        and payload.get("status_code") == "PENDING_APPROVAL"
    ):
        async with connection.transaction():
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="consultation_submitted_for_approval",
                resource_type="consultation",
                resource_id=consultation_id_text,
                detail={
                    "submitted_by_actor_id": str(actor.employee_id),
                    "transition_from": existing["status_code"],
                },
                **request_audit_context(request),
            )
            # Then run the UPDATE SQL with status_code='PENDING_APPROVAL'.

    # Legacy SAVED → COMPLETED direct path: existing 4-gate check stays intact.
    ...
```

The `consultations_complete_checks` anonymous CHECK ensures `suitability_checked` and `explanation_checked` are true before the row can ever reach `COMPLETED`, regardless of which path triggered the transition. PENDING_APPROVAL rows do not need both checks to be true (the CHECK guards COMPLETED only).

### Cardinality contract

| Scenario | Outcome | Audit rows |
|---|---|---|
| PB1 PATCH PENDING_APPROVAL | 200 | `consultation_submitted_for_approval` × 1 |
| PB1 PATCH COMPLETED on own PENDING row | 403 | `four_eyes_violation_blocked` × 1, `same_actor_mutation_blocked` × 0 (Input-6 SKIP) |
| PB2 PATCH COMPLETED on PB1's PENDING row | 200 | `consultation_complete` × 1, `four_eyes_violation_blocked` × 0 |
| PB1 PATCH (no status_code change) on PB1's row | 200 | `same_actor_mutation_blocked` × 1 (v3 carry, detective only) |
| Legacy SAVED → COMPLETED direct (single-actor) | 200 | `consultation_complete` × 1 (NP1-B preserved) |

The "exactly 1 row" cardinality on the preventive path is the binary acceptance test in plan §6 I4.

## Drivers

1. **Preventive over detective (Driver 1)** — regulatory expectation is that the creator cannot self-approve. Detective audit alone leaves the violation in place.
2. **Strictly broader CHECK (Driver 2)** — mirroring V062's DROP/ADD pattern preserves the 7 existing codes and adds exactly one new code. No legacy row becomes invalid.
3. **Backward compatibility (Driver 3)** — the legacy `SAVED → COMPLETED` direct path is preserved. v3 NP1-B (PB non-marketing self-approve via the direct path) keeps passing. The new gate fires only on the new `PENDING_APPROVAL → COMPLETED` transition.

## Alternatives Considered

### Option-B (REJECTED, confidence 0.85) — Boolean `pending_approval` flag

Add `pending_approval BOOLEAN NOT NULL DEFAULT FALSE` and gate `COMPLETED` when the flag is true.

Rejected because:
- State expressiveness is poor: the flag cannot distinguish "submitted by X" from "approved by Y" or "expired without approval".
- Audit derivation requires joining the flag transition history to actor identity, which `consultations` does not record. The state machine column carries that information for free.
- Two columns to keep consistent (`status_code` and `pending_approval`) is exactly the kind of dual SoT this cycle avoids.

### Option-C (REJECTED, confidence 0.90) — Defer to v5

Skip PENDING_APPROVAL this cycle and ship only the same_actor_mutation_blocked detective in more places.

Rejected because:
- The cycle scope explicitly includes the 4-eye preventive control (user verbatim "누락없이").
- The detective control already exists at the v3 carry site; not extending it to preventive means the F8 fail-closed regression remains active in production (no path can exercise the gate).
- Splitting the state machine across two cycles doubles the migration count and the ADR review burden for the same end state.

## Consequences

### Positive

- The 4-eye preventive gate exists with file:LINE evidence in the router and a fresh psql cardinality test (`SELECT COUNT(*) FROM audit_logs WHERE action_code='four_eyes_violation_blocked' AND resource_type='consultation' AND ...`).
- The detective control (v3 carry) stays in place. Both signals fire on the appropriate paths.
- The `consultations_complete_checks` anonymous CHECK is preserved unchanged. The "COMPLETED implies both checks" invariant is untouched.

### Negative

- Frontend has no PENDING_APPROVAL UI state (KycEddPage / ConsultationsPage display rules). Deferred to F-V5-1.
- The preventive emit happens before the `HTTPException(403)`. If the `audit_repo.insert_audit_log` call itself fails (PG down), the request becomes a 5xx instead of a 403. The transaction wrap ensures the audit row is rolled back on any pre-commit failure; the 403 path that produces no audit row is rare and acceptable (Pre-mortem Scenario-3 mitigation #5).

### Risks

- **R1** Migration regression on the 7→8 status CHECK — mitigated by pre-migration distribution query and V005 anonymous CHECK preservation.
- **R9** Input-6 SKIP rule not applied → dual-emit (4-eye + detective on the same path). Mitigated by the cardinality acceptance test "exactly 1 row, zero same_actor_mutation_blocked" (plan §6 I4 + Pre-mortem Scenario-3 mitigation #2).

## Follow-ups

- **F-V5-1** Frontend `PENDING_APPROVAL` display + transition control on KycEddPage / ConsultationsPage.
- **F-V5-3** DOWN script for V076 (`ALTER ... DROP CONSTRAINT ... ADD CONSTRAINT ... CHECK (7-status)`). PoC defers.

## Evidence Anchors (Critic M1 quote)

- `db/migrations/V062__consultation_status_diversification.sql:1-17` — current 7-status SoT after V062.
- `db/migrations/V005__consultations.sql:15-17` — anonymous CHECK `consultations_complete_checks` (preserved mandate).
- `apps/api/harness/api/routers/consultations.py:82-117` — `update_consultation` + v3 B5 detective emit.
- `apps/api/harness/api/routers/consultations.py:103-117` — v3 carry detective `same_actor_mutation_blocked` (NOT transactional, preserved by Input-5 split).
- `apps/api/harness/core/audit.py:130-132` — V071 carry CANONICAL tuple including `four_eyes_violation_blocked` (multi-file emit_source, OQ-V4-CR3).

## Cross-References

- [[endpoint-emit-tracing-required]] (M2).
- [[user-intent-system-wide-vs-page-scoped]] — "누락없이" interpreted as preventive + detective at all relevant sites.
- ADR-017 — `core/identity.py:same_actor()` shared with the same-actor predicate here.
- ADR-019.1 sidecar — AI compliance mode toggle that unblocks marketing-side PENDING_APPROVAL in PoC.
- ADR-002 — email authority and schema contract (unchanged; the consultations gate is independent).
