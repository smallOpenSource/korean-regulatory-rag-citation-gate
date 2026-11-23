# ADR-017 — `kyc_edd_triggers` + `dispute_cases` Previous-Actor Schema (Consolidated)

- **Status**: Accepted (svc-viability-v4 W4, 2026-05-25). Implemented via V073 (`kyc_edd_triggers.previous_actor_id`) + V075 (`dispute_cases.responded_by_actor_id` + `resolved_by_actor_id`) + transaction-wrapped router emits at `routers/kyc_edd.py:reassess+complete` (W1 commit) and `routers/disputes.py:update_dispute_status` (W1 commit). All `same_actor` predicates use `core.identity.same_actor` (ADR-019 cross-ref).
- **Predecessor**: svc-viability-v3 closure handoff §4 follow-up rows 1 (kyc_edd) + 3 (disputes) — both schemas blocked the same-actor invariant emit because mutation actor was not persisted.
- **Cycle**: svc-viability-v4 (ralplan iter-2 APPROVE, 2-cap consensus closure)
- **Plan SoT**: `<repo-root>/.omc/plans/ralplan-wmah-service-viability-v4.md` §4 I1 + §4 I3 + §11.
- **Author lane**: Planner (iter-2) + Architect APPROVE iter-2 + Critic APPROVE iter-2 (M1 file:LINE evidence verbatim quote).

---

## Context

Two routers in the wmah PoC perform mutations on customer-protection ledgers but provide no DB-resident way to compare the *previous* mutation actor against the *current* mutation actor. This blocks the same-actor invariant audit emit (`same_actor_mutation_blocked`) and forces v3 to ship the consultations carry-over detective control only.

1. **kyc_edd_triggers** (`db/migrations/V029__kyc_edd.sql:5-19`) records `reassessor_employee_id` only at `complete`. On `reassess` the column is left NULL. A second `reassess` by the same PB therefore cannot be detected — there is no prior actor recorded on the row.

2. **dispute_cases** (`db/migrations/V028__disputes.sql:1-15`) carries `employee_id` (the opener) but persists no responder or resolver. `routers/disputes.py:127-172 update_dispute_status` runs `UPDATE_DISPUTE_STATUS_SQL` (`apps/api/harness/repositories/disputes.py:35-45`) which writes only `status`, `responded_at`, `resolved_at` — no actor column is updated.

The two follow-ups share an identical shape: *additive nullable UUID column referencing `employees(id)`, populated at the mutation that previously left the actor anonymous*. We bundle them in a single ADR to keep the schema decision rationale colocated.

## Decision

Adopt **Option-A (순수 additive nullable + router responsibility)** for both tables:

### V073 — `kyc_edd_triggers.previous_actor_id`

```sql
/* sql_id: v073_kyc_edd_previous_actor */
ALTER TABLE kyc_edd_triggers
    ADD COLUMN IF NOT EXISTS previous_actor_id UUID
        REFERENCES employees(id)
        DEFAULT NULL;
```

* Pure additive: every existing row stays valid.
* No SQL-side `COALESCE` — the router passes `existing["reassessor_employee_id"]` as `$3` on each reassess/complete cycle.
* On the first ever reassess the value is `NULL`, which the router uses as the same-actor sentinel (`same_actor(actor, None) == False`).

### V075 — `dispute_cases.responded_by_actor_id` + `dispute_cases.resolved_by_actor_id`

```sql
/* sql_id: v075_disputes_actor_tracking */
ALTER TABLE dispute_cases
    ADD COLUMN IF NOT EXISTS responded_by_actor_id UUID
        REFERENCES employees(id)
        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS resolved_by_actor_id UUID
        REFERENCES employees(id)
        DEFAULT NULL;
```

* Two nullable columns instead of a single `last_mutation_actor_id` to keep RESPONDED ↔ RESOLVED transition history disambiguated (OQ-V4-7, planner iter-2 lock).
* Router writes the column matching the new `status` (`$3::uuid` bound parameter on the RESPONDED branch, second `$4::uuid` on the RESOLVED branch).
* The same-actor compare uses `responded_by_actor_id` as the "previous resolver" when the row transitions RESPONDED → RESOLVED.

### Router-side responsibility

The repository layer accepts the `previous_actor_id` (and `responded_by_actor_id`/`resolved_by_actor_id`) values **only as bound parameters**. There is no SQL-side COALESCE, no fallback to `actor_id`, no implicit conversion. Routers must:

1. `SELECT` the existing row before `UPDATE`.
2. Compute the previous actor explicitly (`old_actor = existing.get("reassessor_employee_id")`).
3. Pass it through the repository function as a kwarg.
4. Wrap the SELECT + emit + UPDATE in `async with connection.transaction():` (Input-5).

This keeps the SQL declarative and pins the previous-actor invariant inside the audited code path.

### EXPIRED out-of-scope (Input-4)

`services/disputes.py:9` defines `VALID_STATUSES = ('OPEN','RESPONDED','RESOLVED','EXPIRED')` but the actor-driven transition validator (`validate_dispute_resolve()`, lines 42-47) returns only `RESOLVED|RESPONDED`. EXPIRED is APScheduler-driven (system actor = NULL) and is gated by `services/disputes.py:31` ("`No scheduler is wired in Wave 2 (Stage 7 RUN-09 will attach APScheduler for expiry transitions)`"). V075 therefore covers RESPONDED + RESOLVED only. EXPIRED auto-transition is deferred to F-V5-8 (Stage 7 RUN-09).

## Drivers

1. **Backward compatibility (Driver 1)** — `ALTER ... ADD COLUMN ... DEFAULT NULL` is non-blocking and preserves every existing row + FK + CHECK. v3 audit_v1_workflow_e2e.py NP1/NP1-B/NP1-C must continue PASS after W0b apply.
2. **Single source of truth (Driver 2)** — the column lives on the row it audits; we do not derive the previous actor from `audit_logs` (read latency + race with append-only writes + dual SoT vs the mutation row).
3. **Audit-row cardinality (Driver 3)** — without a DB-resident previous actor, the `same_actor_mutation_blocked` emit cannot fire from the router. Adding the column is the minimum schema change that unlocks the emit semantics defined in V071 (`/* sql_id: v071_security_action_codes */`).

> Time and review burden are explicitly **not** drivers (per [[quality-over-efficiency-recommendation]] reinforced 2026-05-22 / 2026-05-25).

## Alternatives Considered

### Option-B (REJECTED, confidence 0.90) — Derive previous actor from `audit_logs`

Walk back through `audit_logs WHERE resource_type='kyc_edd_trigger' AND resource_id=$1 ORDER BY created_at DESC LIMIT 1`.

Rejected because:
- Read latency: each mutation incurs an additional indexed scan on `audit_logs` (millions of rows).
- Race window: `audit_logs` is append-only and writes through an after-commit hook — a same-transaction read may not see the row yet.
- Dual SoT: the mutation row is canonical; bouncing the comparison through the audit ledger inverts the trust boundary.

### Option-C (REJECTED, confidence 0.80) — History sub-table (`kyc_edd_actor_history`, `dispute_resolver_history`)

A normalized history per row.

Rejected because:
- Schema bloat: two new tables + indexes + FK + truncation policy for what is a single previous-actor lookup.
- Maintenance burden: history pruning, retention contract, schema drift between the two history tables.
- No additional invariant is captured beyond `previous_actor_id` — the row only ever needs one prior actor to evaluate the same-actor predicate.

### Option-D (REJECTED, confidence 0.70) — Single `last_mutation_actor_id` on `dispute_cases`

Collapse RESPONDED and RESOLVED into one column.

Rejected because:
- A dispute can be RESPONDED by PB1 and RESOLVED by PB2; the prior-resolver context is destroyed on transition.
- Future regulatory queries ("who responded vs who resolved") need to be reconstructed from `audit_logs` again, defeating the whole point of putting the actor on the row.

## Consequences

### Positive

- `same_actor_mutation_blocked` emits from kyc_edd reassess+complete and disputes update_status with file:LINE evidence on the router transaction wrap.
- `core/identity.py:same_actor()` (ADR-019 cross-ref) handles the None-on-first-invocation sentinel uniformly across consultations (v3 carry), kyc_edd (V073), dispute (V075).
- The emit semantics match the V071 action_code contract registered in `apps/api/harness/core/audit.py:130-132`. No two-source drift (I8 contract test, plan §4 I8).

### Negative

- Five distinct W*.py emit sites must be wrapped in `async with connection.transaction():` (Input-5). The transaction wrap also rolls back the audit emit on UPDATE failure, which is the intended atomic-pair behavior but changes the audit cardinality compared to the v3 detective (which is *not* transactional and persists the audit row even on a downstream rollback). v3 `consultations.py:108-117` stays as documented carry-over.
- `previous_actor_id IS NULL` on the very first reassess. The same-actor predicate returns `False` for any NULL operand (`core/identity.py:same_actor`), so the emit is correctly suppressed — but the legacy NULL distribution must be confirmed pre-migration (Scenario-1 mitigation #5).

### Risks

- **R1** Migration-driven regression on V029 / V028 row count or FK — mitigated by additive nullable + pre-migration `SELECT COUNT(*) WHERE previous_actor_id IS NULL` (Scenario-1 mitigation #5).
- **R5** PG Patroni transient drop during V073 / V075 ALTER — mitigated by C8 with_retry decorator (`core/db.py`, v3 closure carry).

## Follow-ups

- **F-V5-3** — DOWN script for V073 + V075 (rollback `ALTER ... DROP COLUMN`). PoC defers rollback artifacts per project policy.
- **F-V5-8** — EXPIRED auto-transition same-actor handling (actor=NULL system row). Wait until APScheduler is wired in Stage 7 RUN-09. Until then, `dispute_cases.responded_by_actor_id` and `resolved_by_actor_id` remain `NULL` for EXPIRED rows; the audit predicate returns `False` and skips the emit.
- **F-V5-6** — Lint or pre-commit rule that catches `existing.get("actor_id") == actor.employee_id` direct compares and rewrites them to `same_actor(...)` from `core/identity.py`.

## Evidence Anchors (Critic M1 quote)

- `db/migrations/V029__kyc_edd.sql:5-19` — `kyc_edd_triggers` schema with `reassessor_employee_id` NULLABLE.
- `apps/api/harness/repositories/kyc_edd.py:46-57` — `REASSESS_KYC_EDD_TRIGGER_SQL` (current, no `previous_actor_id`).
- `apps/api/harness/repositories/kyc_edd.py:59-71` — `COMPLETE_KYC_EDD_TRIGGER_SQL` (current, sets `reassessor_employee_id` only).
- `db/migrations/V028__disputes.sql:1-15` — `dispute_cases` schema with no resolver columns.
- `apps/api/harness/repositories/disputes.py:35-45` — `UPDATE_DISPUTE_STATUS_SQL` (current, no actor binding).
- `apps/api/harness/api/routers/disputes.py:127-172` — `update_dispute_status` (current, no same-actor compare).
- `apps/api/harness/services/disputes.py:9` — `VALID_STATUSES` including EXPIRED.
- `apps/api/harness/services/disputes.py:31` — `'No scheduler is wired in Wave 2 (Stage 7 RUN-09 will attach APScheduler for expiry transitions)'` docstring.
- `apps/api/harness/services/disputes.py:42-47` — `validate_dispute_resolve()` returning `RESOLVED|RESPONDED` only.
- `apps/api/harness/api/routers/consultations.py:103-117` — v3 B5 detective `same_actor_mutation_blocked` (carry-over, NOT transactional, documented baseline).
- `apps/api/harness/core/audit.py:130-132` — V071 carry CANONICAL tuple including `same_actor_mutation_blocked`.

## Cross-References

- [[svc-viability-v3-closure]] — predecessor scope.
- [[endpoint-emit-tracing-required]] (M2) — file:LINE evidence mandate for the emit site.
- [[verification-before-completion]] — fresh psql `SELECT COUNT(*) FROM audit_logs WHERE action_code='same_actor_mutation_blocked' AND resource_type IN ('kyc_edd_trigger','dispute_case')` confirms each emit at runtime.
- ADR-019 — `core/identity.py:same_actor()` helper consumed by the same emit sites.
- ADR-018 — sister ADR for ADMIN cross-admin regen audit (different invariant, kept separate to avoid 4-eye semantic conflation).
