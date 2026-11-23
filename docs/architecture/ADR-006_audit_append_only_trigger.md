# ADR-006 Audit Log Append-Only Invariant (V008 + V019 Layered Design)

## Status
Accepted as a Stage 0.5 architecture contract. Layer A (row-level UPDATE/DELETE denial) is
**already implemented** in V008; Layer B (statement-level TRUNCATE denial + table privilege
REVOKE) is scheduled for V019 in Stage 1; Layer C (retention partitioning) is deferred to Stage 7
runbook RUN-08. Authored 2026-05-17 under RALPLAN-DR Iteration 2 Wave 1 Stage 0.5 (P-5 reframe
over V008 prior art); source-of-truth REG-06 §5 / REG-04 §3-bis Audit Backbone.

## Context
The PoC's audit chain must be tamper-evident under SOC2-style review and under regulator review
(전자금융감독규정 §37 5-year retention, REG-01 §3.1 자본시장법 §59 / REG-02 §3 권유기록
10-year subset). Append-only is the foundational invariant: any audit row, once written, can be
read but cannot be modified or removed before its retention window.

V008 (`db/migrations/V008__audit_email_ai.sql`) **already** installed the row-level denial layer
during the early schema work. A previous draft of the plan suggested V019 redesign the audit
triggers; this is incorrect and risks the executor re-creating what already exists. This ADR
therefore re-frames V019 as a **narrow gap-fill** over V008's prior art.

## Drivers
- REG-04 §3-bis Audit Backbone: every AI/auth/governance action emits an audit row that
  attackers and operators alike cannot mutate.
- REG-06 §5 / §7: SOC2 immutable WORM log; SoD evidence pack depends on append-only invariant.
- REG-01 §3.1 / REG-02 §3: regulator-mandated retention (5y general, 10y subset).
- Operational reality: `psql` superuser sessions can run `TRUNCATE` and `REVOKE` even when
  triggers block UPDATE/DELETE; closing this gap requires both statement-level triggers and
  table-privilege management.
- Avoid data loss: partitioning a non-empty `audit_logs` table mid-PoC has documented failure
  modes (constraint violations, dropped row count on bad PARTITION BY); partition work is moved
  to a runbook so it executes offline post-acceptance.

## Decision — Three-Layer Append-Only Architecture

### Layer A — Row-Level UPDATE/DELETE Denial (V008, prior art, retained as-is)
V008 has **already** installed the following objects on the `audit_logs` table — verified at
`db/migrations/V008__audit_email_ai.sql:52-75`:

```sql
/* sql_id: create_prevent_audit_mutation_fn */
CREATE OR REPLACE FUNCTION prevent_audit_log_update_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs are append-only';
END;
$$;

/* sql_id: create_audit_no_update_trigger */
DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;

/* sql_id: create_audit_no_update_trigger_body */
CREATE TRIGGER trg_audit_logs_no_update
BEFORE UPDATE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update_delete();

/* sql_id: create_audit_no_delete_trigger */
DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;

/* sql_id: create_audit_no_delete_trigger_body */
CREATE TRIGGER trg_audit_logs_no_delete
BEFORE DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update_delete();
```

**These objects are retained as-is.** Any later migration that drops, replaces, or alters them is
forbidden without an ADR-006 amendment. The Stage 1 regression test
(`tests/test_audit_append_only.py`, T315) asserts that:
- the function `prevent_audit_log_update_delete()` exists,
- the triggers `trg_audit_logs_no_update` and `trg_audit_logs_no_delete` exist on `audit_logs`
  with `tgenabled='O'` (enabled / origin),
- attempting `UPDATE audit_logs SET ...` raises `audit_logs are append-only`,
- attempting `DELETE FROM audit_logs WHERE ...` raises `audit_logs are append-only`.

**No executor may re-create the V008 triggers in V019 or any later migration.** Re-creating them
would mask drift from V008 (e.g., if someone disabled them) and would suggest the prior art was
absent. The regression test is the canonical drift detector.

### Layer B — Statement-Level TRUNCATE Denial + Privilege REVOKE (V019, new in Stage 1)
V008's `FOR EACH ROW` triggers do **not** fire on `TRUNCATE` (PostgreSQL semantics — `TRUNCATE`
is statement-level and bypasses row-level triggers). Layer B closes this gap with a
**narrow, additive** migration. Scope of V019 (and only V019) on `audit_logs`:

1. **Statement-level TRUNCATE trigger** (`trg_audit_logs_no_truncate`):
   ```sql
   /* sql_id: create_audit_no_truncate_fn */
   CREATE OR REPLACE FUNCTION prevent_audit_log_truncate()
   RETURNS trigger
   LANGUAGE plpgsql
   AS $$
   BEGIN
       RAISE EXCEPTION 'audit_logs TRUNCATE denied (PoC append-only invariant)';
   END;
   $$;

   /* sql_id: create_audit_no_truncate_trigger */
   DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;

   /* sql_id: create_audit_no_truncate_trigger_body */
   CREATE TRIGGER trg_audit_logs_no_truncate
   BEFORE TRUNCATE ON audit_logs
   FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_log_truncate();
   ```

2. **Privilege REVOKE + role-aware GRANT** (per REG-05 §4 Stage 1 T290 account separation):
   ```sql
   /* sql_id: audit_logs_revoke_mutation */
   REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;

   /* sql_id: audit_logs_grant_insert_app */
   GRANT INSERT ON audit_logs TO harness_app;

   /* sql_id: audit_logs_grant_insert_batch */
   GRANT INSERT ON audit_logs TO harness_batch;

   /* sql_id: audit_logs_grant_select_audit */
   GRANT SELECT ON audit_logs TO harness_audit;

   /* sql_id: audit_logs_grant_select_admin */
   GRANT SELECT ON audit_logs TO harness_admin;
   ```

Privilege matrix after V019:

| role | INSERT | SELECT | UPDATE | DELETE | TRUNCATE |
|---|:---:|:---:|:---:|:---:|:---:|
| `harness_app` | ✅ | ❌ (except via audit-chain-hash verification path under a dedicated view) | ❌ | ❌ | ❌ |
| `harness_batch` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `harness_audit` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `harness_admin` | ❌ | ✅ | ❌ | ❌ | ❌ (DDL on other tables allowed, but not on audit_logs) |
| `PUBLIC` | ❌ | ❌ | ❌ | ❌ | ❌ |

**V019 SCOPE IS STRICTLY THESE TWO ITEMS — TRUNCATE trigger + REVOKE/GRANT.** V019 must not
recreate V008 row-level triggers, must not add new columns, must not partition. Any other change
to audit_logs in Stage 1 is forbidden under this ADR.

The Stage 1 regression test (T315) covers all four denial paths:
- row-level UPDATE → `audit_logs are append-only` (V008 prior art);
- row-level DELETE → `audit_logs are append-only` (V008 prior art);
- statement-level TRUNCATE → `audit_logs TRUNCATE denied (PoC append-only invariant)` (V019);
- privilege test: connect as `harness_app`, attempt `DELETE FROM audit_logs WHERE 1=1`, expect
  `permission denied for table audit_logs` (the REVOKE catches the attempt before the trigger
  fires; both controls are layered).

The regression also asserts the V008 trigger names still exist (prior-art preservation check).

### Layer C — Retention Partitioning (deferred to Stage 7 RUN-08)
- **What:** 5-year (general audit) vs 10-year (regulator-mandated subset — REG-01 §3.1 자본시장법
  §59 + REG-02 §3 권유기록·면담기록) partition boundary.
- **Why deferred:** Partitioning a non-empty `audit_logs` table mid-PoC has documented failure
  modes:
  - `PARTITION BY RANGE (created_at)` requires the partition key be part of the primary key /
    uniqueness constraints; existing PK may need restructuring.
  - Migrating existing rows to partitioned children requires a window of write-blocking or a
    careful detach/attach dance; PoC autopilot lanes cannot tolerate write-blocking.
  - Recovery from a partition migration failure is hard; doing it offline post-acceptance under
    change control is safer.
- **Where:** `docs/runbooks/RUN-08_audit_retention_partitions.md` (new, Stage 7 deliverable).
  RUN-08 will document:
  - The two-tier partition scheme (10y subset selected by `action_code` allowlist; 5y general).
  - The offline migration script with row-count parity assertions before/after.
  - The hash-chain re-anchor procedure (if audit chain hashes are introduced before Stage 7).
  - Rollback plan if partition migration fails mid-way.
- **What V019 does NOT do:** V019 does **not** partition. The only Stage 1 deliverables on
  `audit_logs` are the Layer B TRUNCATE trigger and the REVOKE/GRANT statements.

## Alternatives Considered
- **Re-create V008 triggers in V019 to make append-only "self-contained" in Stage 1**: rejected
  — re-creation invites drift, breaks the prior-art preservation contract, and makes the
  regression test ambiguous (which migration owns the trigger?).
- **TRUNCATE trigger as `FOR EACH ROW`**: rejected — PostgreSQL bypasses row triggers on
  TRUNCATE; only `FOR EACH STATEMENT` fires on `BEFORE TRUNCATE`.
- **Event trigger on database level instead of table trigger**: considered but rejected for PoC
  — event triggers fire on DDL/DDL-like operations and would catch TRUNCATE table-wide, but they
  require superuser to create and would constrain other tables' legitimate TRUNCATE; the
  table-scoped `BEFORE TRUNCATE` trigger is the minimum-surface fix.
- **Partition in V019**: rejected — too risky mid-PoC (see §"Why deferred" above); RUN-08
  performs it offline.
- **Audit-chain hash column in V019**: out of scope for this ADR. Hash-chain integrity may be
  introduced separately; this ADR governs only the append-only invariant.
- **Revoke ALL privileges from PUBLIC and re-grant individually**: rejected as too broad —
  REVOKE-then-GRANT semantics work safely only when we know the full set of dependent objects;
  the targeted `REVOKE UPDATE, DELETE, TRUNCATE` plus explicit GRANT INSERT/SELECT is auditable
  and narrow.

## Why Chosen
- The V008 prior art is correct and complete for its scope (row-level UPDATE/DELETE); rewriting
  it would be churn without benefit.
- Layer B's two-item scope (TRUNCATE trigger + REVOKE/GRANT) is the smallest viable closure of
  V008's documented gaps.
- Deferring partitioning preserves data integrity during PoC autopilot runs and gates the
  high-risk operation behind a change-controlled runbook.
- Defense in depth: privilege REVOKE catches role-scoped attempts (cheap, fast); triggers catch
  superuser/operator attempts (correct, raises clear exceptions). Two independent controls.

## Consequences
- The audit chain is tamper-evident under all four denial paths (UPDATE/DELETE/TRUNCATE
  row+statement + role-privilege) before any Stage 2+ code lands.
- DBA / runbook operators **cannot** clean the `audit_logs` table by routine TRUNCATE/DELETE
  even under a superuser session. Any need to remove audit data (e.g., GDPR right-to-erasure
  hypothetical) requires a documented, change-controlled procedure that itself emits audit rows.
- The Stage 1 regression test becomes a permanent guardrail — any later migration that
  accidentally drops the V008 triggers or grants UPDATE/DELETE/TRUNCATE will fail CI.
- `harness_app` has no SELECT on `audit_logs` outside the dedicated audit-chain-hash verification
  view (Stage 1 §10), reducing the blast radius if the application is compromised.
- The audit-chain-hash verification path, when introduced, must be a SECURITY DEFINER view or
  function that returns only the hash chain summary, not raw rows.
- Stage 7 RUN-08 inherits the partition design responsibility; until then, `audit_logs` is a
  single unpartitioned table, sized to handle PoC traffic (≤ ~10M rows is fine on Postgres 17).

## Follow-ups
- T293 — V019 SQL implementation (TRUNCATE trigger + REVOKE/GRANT only; this ADR is the spec).
- T315 — `tests/test_audit_append_only.py` covering four denial paths + V008 prior-art
  preservation assertions.
- T290 — PostgreSQL account separation (`harness_app/batch/audit/admin`) provisioning SQL in
  `db/setup/roles.sql`; V019 GRANT depends on these roles existing.
- Stage 7 RUN-08 — retention partitioning runbook (5y / 10y).
- Optional later: audit-chain hash column + verification view (separate ADR if introduced).

## Cross-References
- **BIZ-06 Compliance**: every governance/compliance action emits an audit row; this ADR makes
  those rows tamper-evident.
- **SEC-01 Auth Spec**: role separation defines the actors that can INSERT (harness_app/batch)
  vs SELECT (harness_audit/admin); refresh-token reuse-detection audit rows are protected by
  this invariant.
- **AI-04 RAG Spec**: BLOCKED `ai_outputs` rows always pair with an `audit_logs` row; the
  append-only invariant ensures fail-closed evidence cannot be scrubbed by an LLM01 attacker.
- **ADR-001 WebSocket**: `audit.tail` channel surfaces audit_logs rows read-only via
  AUDIT_VIEWER; the WS payload is the same safe-detail projection as `/audit-logs`, never the
  raw row.
- **ADR-002 Email**: every email state transition emits an audit row that inherits this
  invariant; the redaction filter ensures `detail_json` carries no PII even though the row is
  itself immutable.
- **ADR-003 Dependency Gate**: no ORM, no migration framework — V019 lands as raw SQL via the
  custom migrator, sql_id comments mandatory.
- **ADR-004 PoC_AUTO_APPROVAL**: every auto-approval and abort row inherits this invariant; SoD
  evidence pack relies on the rows being unfalsifiable.
- **ADR-005 Dual-LLM Quarantine**: fail-closed paths emit audit rows; this ADR ensures those
  rows cannot be deleted to hide LLM01 evidence.
- **ADR-007 Validator Contracts**: `generate_sod_evidence_pack.py` and
  `generate_seven_principles_report.py` both depend on the audit_logs append-only invariant —
  their output's integrity is downstream of this ADR.
- **REG-01 §3.1 / REG-02 §3 / REG-06 §5 / REG-04 §3-bis**: source-of-truth for retention and
  immutability requirements.
- **`db/migrations/V008__audit_email_ai.sql:52-75`**: prior-art file:lines reference for Layer A.
