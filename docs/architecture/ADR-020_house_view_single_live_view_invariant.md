# ADR-020 — `house_views` Single-Global-Live-View Invariant (legacy↔lifecycle 상호배타 공식화)

- **Status**: Accepted (P2 follow-up, 2026-05-31). Implemented via `LIVE_HOUSE_VIEW_STATUSES`/`LIVE_HOUSE_VIEW_STATUS_IN` SoT constant + `assert_single_live_house_view()` guard wired into BOTH activation transactions (`activate_house_view` legacy + `activate_lifecycle_house_view` T16) + dashboard live-set SoT unification with import-time drift guard + router `structured_http_exception(409, ErrorCode.house_view_single_live_invariant, …)` mapping (new `ErrorCode` member; 409 was previously unmapped in `_STATUS_TO_CODE` and would have fallen back to `internal_error`) + a contract test that asserts a single live view across mixed activation sequences and that the guard fires on a per-tuple/global collision. **F1 DB-level backstop implemented (§11, 2026-05-31)**: V082 partial UNIQUE index `idx_house_views_single_live` (constant-key `((true))` + the non-fixture predicate) forbids even a direct-write second non-fixture live row; the activation functions translate its `UniqueViolationError` back to `SingleLiveHouseViewViolation` so the router still returns 409.
- **Predecessor**: `docs/dev/DEV-11_p2_data_hygiene_close_out.md` §9-b caveat — "legacy(global supersede) vs T16 lifecycle(per-tuple ACTIVATED)는 상호배타 운영 모드 … 현재 readers가 global-single-row(LIMIT 1)라 inert; 향후 per-tuple live view를 노출하면 legacy global supersede 재검토 필요". This ADR formalizes that inert caveat as an enforced runtime invariant.
- **Scope**: house_view activation write paths + live-view readers. No schema change (additive guard at the application layer). No endpoint disabled.

---

## Context

`house_views` carries two activation models that evolved in parallel:

1. **Legacy `/activate`** (`activate_house_view`, ADMIN-only): `DRAFT`/`PENDING_REVIEW` → `ACTIVE`, after a **global** `SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL` (`WHERE status_code IN ('ACTIVE','ACTIVATED') AND id <> $1`) that retires every other live view regardless of segment. Asserts a single GLOBAL live house view. Legacy rows leave `market`/`asset_class`/`region` NULL.
2. **T16 `/activate-lifecycle`** (`activate_lifecycle_house_view`, ADMIN-only): `REVIEWED` → `ACTIVATED`, after a **per-tuple** `ARCHIVE_ACTIVE_TUPLE_SQL` that archives only the same `(market, asset_class, region)`. Asserts a single live view PER segment tuple.

The live-view readers — `GET_ACTIVE_HOUSE_VIEW_SQL` and the dashboard `latest_house_view` CTE — match `status_code IN ('ACTIVE','ACTIVATED')`, exclude test fixtures, and `ORDER BY activated_at DESC … LIMIT 1`. They return exactly one global row (newest activation wins) and take no segment-tuple parameter.

These two models are **mutually exclusive**:

- Under legacy/global, exactly one live view exists; the per-tuple columns are unused.
- Under T16/per-tuple, N live views can coexist (one per tuple) — but the global-single readers collapse them to "newest wins" while `LIST` would surface all of them.
- A legacy `/activate` global supersede destroys every per-tuple `ACTIVATED` row; a lifecycle `/activate-lifecycle` of a fresh tuple leaves any other-tuple live view (including a global NULL-tuple `ACTIVE`) untouched, producing **two simultaneously-live views** that the readers do not represent as such.

### Latent index inconsistency (surfaced during this work)

The `SUPERSEDE` comment previously claimed "`idx_house_views_one_active` allows exactly one ACTIVE". That is **incorrect** for the current index:

- `V004__house_views.sql:25` originally defined `idx_house_views_one_active ON house_views(status_code) WHERE status_code='ACTIVE'` — a UNIQUE index on a single-valued column → a true GLOBAL single-ACTIVE constraint.
- `V035__house_view_lifecycle.sql` DROPped it and created `idx_house_views_one_activated_per_tuple ON (market, asset_class, region) WHERE status_code='ACTIVATED' AND market IS NOT NULL` (per-tuple).
- `V040__restore_legacy_active_index.sql` re-created the SAME NAME with a DIFFERENT definition: `ON (market, asset_class, region) WHERE status_code='ACTIVE'`. Because legacy rows leave the tuple NULL and PostgreSQL treats NULLs as distinct in unique indexes, this index does NOT bound the count of NULL-tuple `ACTIVE` rows. The global-single guarantee is therefore **procedural** (the SUPERSEDE clears everything first), never an enforced DB constraint.

### Current runtime reality

A live-DB snapshot (2026-05-31) showed exactly one `ACTIVE` row with a NULL tuple and zero `ACTIVATED` rows; the V052 dashboard fixture and every house_view test use a NULL tuple (`tests/test_house_view_active_status_unification.py:73` leaves `market` NULL explicitly). The entire PoC operates in effectively-global mode, so the per-tuple machinery is present but never exercised with distinct non-NULL tuples. The caveat is real but inert — exactly the condition that lets a guard be added without breaking any current flow.

## Decision

Adopt **Option 1 — invariant unification + runtime guard, no endpoint disabled** (user-selected, 2026-05-31).

### 1. Canonical invariant

> The live-view readers expose at most one **non-fixture** global live house view. `canonical = 전역-단일 live view at read`.

### 2. Live-set single source of truth

`apps/api/harness/repositories/house_views.py`:

```python
LIVE_HOUSE_VIEW_STATUSES: tuple[str, ...] = ("ACTIVE", "ACTIVATED")
LIVE_HOUSE_VIEW_STATUS_IN = "(" + ", ".join(f"'{s}'" for s in LIVE_HOUSE_VIEW_STATUSES) + ")"
```

`SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL`, `GET_ACTIVE_HOUSE_VIEW_SQL`, `ARCHIVE_ACTIVE_TUPLE_SQL`, and `COUNT_LIVE_HOUSE_VIEWS_SQL` all interpolate `LIVE_HOUSE_VIEW_STATUS_IN`. `repositories/dashboard.py` imports the same constant, derives its `replace()` target from it, and raises a `RuntimeError` at import time if the dashboard CTE literal drifts from the SoT (so a future edit cannot silently desync the dashboard live-set from the readers).

### 3. Runtime guard (the tripwire)

```python
async def assert_single_live_house_view(connection: Any) -> None:
    row = await fetch_one(connection, COUNT_LIVE_HOUSE_VIEWS_SQL)
    live_count = int(row["n"]) if row else 0
    if live_count > 1:
        raise SingleLiveHouseViewViolation(
            f"house_view single-live invariant violated: {live_count} non-fixture live views"
        )
```

`COUNT_LIVE_HOUSE_VIEWS_SQL` counts the rows the readers would surface (same live-set + same `NON_FIXTURE_HOUSE_VIEW_PREDICATE`). Both activation functions call the guard **inside their existing transaction**, after the write:

- `activate_house_view`: after the global SUPERSEDE + `ACTIVATE_HOUSE_VIEW_SQL` (defensive — should always pass since SUPERSEDE is global).
- `activate_lifecycle_house_view`: after the per-tuple ARCHIVE + `ACTIVATE_REVIEWED_HOUSE_VIEW_SQL` — this is where a per-tuple `ACTIVATED` left next to a different-tuple live view trips the guard and rolls the activation back.

The router maps `SingleLiveHouseViewViolation` → `structured_http_exception(409, ErrorCode.house_view_single_live_invariant, "activation would leave more than one live house view")` on both endpoints. A new `ErrorCode.house_view_single_live_invariant` member is added because `_STATUS_TO_CODE` has no 409 entry — a plain `HTTPException(409, detail=…)` would render `error_code: internal_error`, whereas the codebase convention for 409s (`four_gate_not_passed`, `idempotency_key_*`) is a domain-specific `ErrorCode` via `structured_http_exception`. The 409 envelope is therefore `{error_code: "house_view_single_live_invariant", message: …, request_id: …}`.

### Why fixtures are excluded from the count

The readers exclude test fixtures (`NON_FIXTURE_HOUSE_VIEW_PREDICATE`), so a fixture live row is invisible at read. Counting only non-fixture rows keeps the guard aligned with "single live view AT READ" and ensures QA-probe fixtures never trip it.

## Drivers

1. **Truthful to the deployed contract (Driver 1)** — the readers are global-single (LIMIT 1, newest-wins, no tuple param). The canonical invariant simply names what the readers already guarantee and makes both write paths uphold it.
2. **Non-breaking (Driver 2)** — every current flow operates with NULL tuples and a single live view, so the guard never fires today. It only fires on a genuine invariant violation (a future per-tuple/global collision), which is precisely the "future per-tuple exposure → revisit" trigger the §9-b caveat asked for.
3. **Single SoT, no drift (Driver 3)** — the live-set literal existed in five places across two files. Collapsing it to one constant (+ a dashboard drift guard) removes the silent-desync risk that lets a reader and a write path disagree on what "live" means.

## Alternatives Considered

### Option 2 (REJECTED, confidence 0.82) — config-gated mutually-exclusive modes

Add `HOUSE_VIEW_ACTIVATION_MODE` env (`legacy_global` | `lifecycle_per_tuple`); the non-active endpoint returns 409.

Rejected because the default necessarily disables one endpoint, breaking the many existing T16 / P2-3 / smoke tests that call `/activate-lifecycle` (and the legacy tests that call `/activate`). The blast radius (mode-setting every affected test) outweighs the benefit, and a config switch is a heavier contract than the inert caveat warranted.

### Option 3 (REJECTED, confidence 0.78) — collapse to a single canonical path

Pick global-single as the only model and deprecate `/activate-lifecycle`'s per-tuple semantics (make its archive global, or 410 the endpoint).

Rejected because it discards the richer T16 lifecycle (DRAFT→GENERATED→REVIEWED→ACTIVATED→ARCHIVED with AI generation metadata + `faithfulness_json`, which P2-3 depends on) and changes the behavior of a tested endpoint. It also forecloses a future per-tuple reader without a code path to support it.

### Option 4 (REJECTED, confidence 0.70) — ADR/documentation only

Document the invariant + add a test, but no runtime enforcement. Rejected because the user explicitly asked to *formalize* (공식화) the exclusivity, not merely record it; a guard makes the contract enforced rather than aspirational.

## Consequences

### Positive

- The legacy↔lifecycle mutual exclusivity is an enforced runtime invariant, not an inert convention. A per-tuple `ACTIVATED` can no longer silently co-exist with a global `ACTIVE`.
- The live-set definition has one SoT; readers and write paths cannot drift.
- Zero schema change, zero endpoint removed, zero migration. Existing NULL-tuple flows are unaffected.
- The misleading SUPERSEDE comment is corrected to state the true (procedural) enforcement.

### Negative / Limits

- ~~The guard is an application-layer invariant, not a DB constraint. A direct SQL writer (bypassing the activation functions) can still create two live rows.~~ **Closed by F1 (§11, V082)**: a partial UNIQUE index now forbids a second non-fixture live row at the DB layer, regardless of write path. The app guard remains the primary SoT / clean-error source; the index is the backstop. Note the index is STRICTER than the guard — it forbids even a *transient* second non-fixture live row within a transaction (the guard only checks post-write), so direct-insert test fixtures that staged two live rows had to clear the live set first.
- ~~A blocked activation returns 409 but emits no audit row.~~ **Closed by F2 (§12, V083)**: a refused activation now emits an append-only `house_view_activation_blocked` audit row (registered across the three sources) on a fresh transaction in the router's except handler, so the refusal persists as evidence even though the activation rolled back.

### Risks

- **R1** — If a future change exposes per-tuple live views in the readers (a tuple-parameterised reader), the canonical invariant itself must be revised (it would no longer be global-single). This ADR is the explicit revisit trigger; the guard would need to become per-tuple-scoped at that point.

## Follow-ups

- **F1 (DB-level hardening)** — ✅ **Implemented 2026-05-31 (V082, §11).** The constant-key `((true))` partial-unique-index idiom was validated on the target PG before applying.
- **F2 (audit on block)** — ✅ **Implemented 2026-05-31 (V083, §12).**
- **F3 (per-tuple reader)** — if per-tuple live views are ever surfaced, revisit this invariant + the guard scope (R1).

## Evidence Anchors

- `apps/api/harness/repositories/house_views.py` — `LIVE_HOUSE_VIEW_STATUSES`/`LIVE_HOUSE_VIEW_STATUS_IN` SoT; `SingleLiveHouseViewViolation`; `COUNT_LIVE_HOUSE_VIEWS_SQL` (`sql_id: count_live_house_views`); `assert_single_live_house_view`; guard call inside `activate_house_view` (legacy) and `activate_lifecycle_house_view` (T16).
- `apps/api/harness/repositories/dashboard.py` — `LIVE_HOUSE_VIEW_STATUS_IN` import + `_LIVE_HOUSE_VIEW_WHERE` replace target + import-time drift `RuntimeError`.
- `apps/api/harness/api/routers/house_views.py` — `except house_repo.SingleLiveHouseViewViolation → structured_http_exception(409, ErrorCode.house_view_single_live_invariant, …)` on both `/activate` and `/activate-lifecycle`.
- `apps/api/harness/core/error_codes.py` — `house_view_single_live_invariant` member; `apps/api/harness/core/errors.py:26` `_STATUS_TO_CODE` (no 409 entry → the reason a structured code is required).
- `db/migrations/V004__house_views.sql:25` (original global one-active), `V035__house_view_lifecycle.sql` (drop + per-tuple index), `V040__restore_legacy_active_index.sql` (per-tuple `idx_house_views_one_active`, NULL-permissive).
- `tests/test_house_view_active_status_unification.py` — contract tests (single-live across mixed activations + guard-fires-on-collision).

## Cross-References

- `docs/dev/DEV-11_p2_data_hygiene_close_out.md` §9-b (caveat this ADR closes), §10 (compliance-notice sibling close-out).
- [[endpoint-emit-tracing-required]] — guard + readers were verified by direct code-path read, not spec inference.
- [[verification-before-completion]] — fresh psql live-state snapshot + contract test + live HTTP smoke.
- ADR-018 — sibling house_view audit ADR (cross-admin regeneration); different concern, same domain.

## 11. F1 — DB-level backstop index (2026-05-31, V082)

The application guard is the primary SoT, but it only governs the two activation
functions. F1 adds a DB-level partial UNIQUE index so a second non-fixture live row
is impossible regardless of write path (a direct seed, a manual psql, a future code
path that bypasses the activation functions).

### Idiom validation (before applying)

The "at most one row matching a predicate" constraint needs a UNIQUE index whose key
is constant across all matching rows. The `((true))` constant-key idiom was validated
on the target PG (rollback transactions) before the migration was written:
- `CREATE UNIQUE INDEX … ON house_views ((true)) WHERE <live + non-fixture>` is accepted and creates against current data (1 non-fixture live row).
- A second non-fixture live row raises `duplicate key value … Key ((true))=(t) already exists`.
- A fixture (e.g. period_code `RALPH-QA`) live row is ALLOWED — excluded by the predicate, mirroring the readers.

### Migration

`db/migrations/V082__house_view_single_live_index.sql` (`sql_id: house_view_single_live_index`,
`migration_versions` version 82) creates `idx_house_views_single_live` with the
`((true))` key and a WHERE predicate that mirrors `LIVE_HOUSE_VIEW_STATUS_IN` +
`NON_FIXTURE_HOUSE_VIEW_PREDICATE`. The predicate is a frozen copy (an index WHERE
cannot reference the Python constant); if the Python non-fixture predicate changes,
a follow-up migration must update the index. The app guard remains the SoT.

### Error-contract preservation

The index fires on the activation `UPDATE` itself (e.g. `ACTIVATE_REVIEWED_HOUSE_VIEW_SQL`
creating a second live row) — BEFORE the app guard's post-write `COUNT` runs. Raw, that
would surface as an unhandled `asyncpg.UniqueViolationError` → 500. So both activation
functions wrap the activate write and translate a violation of `idx_house_views_single_live`
(`exc.constraint_name`) back into `SingleLiveHouseViewViolation`, which the router already
maps to 409. The 409 contract is therefore identical whether the app guard or the DB index
catches the collision.

### Stricter-than-guard consequence

The index forbids even a *transient* second non-fixture live row inside a transaction,
whereas the app guard only checks after the activation write. Direct-insert test fixtures
that previously staged two non-fixture live rows (e.g. inserting a prior `ACTIVATED` next
to the live seed before calling legacy `/activate`) now had to clear the live set first.
This is intended: the invariant is "never two non-fixture live rows", not "not two after
an activation".

The stricter semantics surfaced a **real latent defect** during adversarial review (NOT
"by design"): on a *fresh* DB the documented bootstrap (`db/migrator.py` then `db/seed.py
--profile full-mvp`) aborted. V052's 2099Q4 `ACTIVATED` dashboard fixture is non-fixture
and survives the migrations as the single non-fixture live row; `seed_30_workflows.sql`'s
supersede cleared only `'ACTIVE'`, so when it inserted its own 2026M05 `ACTIVE` row the
two non-fixture live rows tripped `idx_house_views_single_live` and the one-transaction
seed aborted. (The seed integration test missed it because it runs against the shared
dirty DB where V052 is already `ARCHIVED`, never exercising the fresh path.) **Fix**:
`seed_30_workflows.sql`'s house_view supersede now clears `IN ('ACTIVE','ACTIVATED')`,
mirroring `SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL` — verified by a real-statement rollback repro
(fresh state → fixed supersede clears V052 → seed insert → 1 non-fixture live, no
violation) and pinned by `test_seed_30_supersede_clears_activated_for_v082_bootstrap`. A
genuine 2-non-fixture-live seed/migration would still fail — correctly, as an invariant
violation to fix at the source, not a reason to weaken the index.

### Verification

`((true))` idiom + enforcement validated on target PG (BLOCK A/B/C rollback) · V082 applied,
`migration_versions` max = 82 · `pytest tests/test_house_view_active_status_unification.py`
6 passed (incl `test_db_index_rejects_second_non_fixture_live`, which skips if V082 absent) ·
house_view sweep 23 passed · live HTTP smoke 7/7 (collision now routes DB-index → translate →
409 `house_view_single_live_invariant`, happy 200, rollback, restore) · ruff 0 new.

## 12. F2 — refusal audit (house_view_activation_blocked, 2026-05-31, V083)

A refused activation (the single-live invariant rolls it back and returns 409) now emits
an append-only `house_view_activation_blocked` audit row so the refusal leaves a ledger
entry. Registered across the three sources (two-source rule + OBS-02):

1. **DB** — `db/migrations/V083__house_view_activation_blocked_audit_code.sql` INSERTs the code
   into `audit_action_codes` (`audit_logs.action_code` is FK-constrained). `migration_versions` 83.
2. **Python** — `core/audit.py::CANONICAL_AUDIT_ACTION_CODES` carries it (`require_audit_action`
   raises `ValueError` otherwise). The DB↔CANONICAL symmetric-diff drift gate
   (`tests/test_audit_action_code_drift.py`) passes.
3. **Doc** — `docs/observability/OBS-02_audit_action_codes.md` detailed-section row
   (emit_source `routers/house_views.py` `/activate` + `/activate-lifecycle`; resource_type
   `house_view`; meta_keys `reason`, `endpoint`).

### Emit point — fresh transaction, post-rollback

Both `/activate` and `/activate-lifecycle` except handlers, on catching
`SingleLiveHouseViewViolation`, emit the audit row inside `async with connection.transaction()`
BEFORE raising the 409. This is essential: the repo activation raised inside its OWN
`connection.transaction()`, which rolled back; the router connection is a bare pooled
connection (not in an outer transaction), so the except handler's `transaction()` is a real
top-level BEGIN/COMMIT that persists the audit row independently of the rolled-back activation.
Verified end-to-end against the real repo + real `audit_repo` (activation rolled back / REVIEWED
stayed REVIEWED, audit row committed +1) — the append-only `audit_logs` trigger even blocked a
cleanup DELETE of the row, proving persistence/immutability. `detail` = `{reason:
single_live_invariant, endpoint: activate|activate-lifecycle}`.

### Verification

V083 sha256 == `migration_versions` checksum (version 83) · drift gate passes · F2 live smoke 5/5
(collision 409, activation rolled back, `house_view_activation_blocked` +1 with correct detail) ·
house_view sweep 24 passed · ruff 0 new · 3-lens adversarial review GO (0-refuted). Two unrelated
pre-existing failures (reproduce with F2 stashed, NOT caused by F2): `test_every_terminal_ai_job_has_audit_call_started`
(≈219 terminal ai_jobs from the wave_g operator generate-run with no AI_CALL_STARTED) and
`test_canonical_audit_codes_match_docs` (the prior 9 W2-I8 OBS-02 doc-sync gap; `house_view_activation_blocked`
is in neither the missing nor the duplicate list — F2 does not worsen it).
