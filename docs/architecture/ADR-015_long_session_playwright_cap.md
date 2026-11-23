# ADR-015 — Long-session Playwright UI matrix audit cap policy

- **Status**: Accepted (svc-viability-v3 C9, 2026-05-25). svc-viability-v4 W4 amend: `tests/benchmark_per_cell_login.py` introduced as the per-cell login overhead measurement utility (10 cells × N iter → p50/p95/max ms JSON). Actual benchmark run is deferred to operator (Playwright env: `DISPLAY=:99` + `/opt/playwright-browsers`); the file is committed so the measurement is reproducible. p95 ≤ 3 s ⇒ ADR-015 cap policy is confirmed adequate; p95 > 3 s ⇒ PARTIAL with split-policy follow-up (per-session pool model in v5).
- **Predecessor**: ADR-009 §Wave G (v8 state-graph-traversal), ADR-010 (service viability baseline)
- **Cycle**: svc-viability-v3 (PARTIAL closure carry-over from svc-viability-v2 T2-4 environmental ceiling), svc-viability-v4 W4 (benchmark utility)

## Context

`scripts/audit_v1_ui_matrix.py` walks 112 cells (role × route × interaction).
A single ADMIN-role session is reused across the entire run via one
`browser.new_context()` + one `login()` invocation. In the
svc-viability-v2 closure cycle (2026-05-24) we observed:

- short worker-3 run (~5min, 312s): **106/112 PASS**
- long lead direct fire run (~50min, 2959s): **0/112 PASS** —
  79 cells flipped to `landed_on_login_with_access` because the JWT
  expired mid-traversal.

Backend `/health`, frontend, Mailpit, and Patroni were all live
throughout. The failure was an artifact of single-session reuse
crossing the JWT expiry window, not a defect in the application
under test.

`[[audit-e2e-environmental-ceiling]]` documents the ceiling around
87-88/112 even with single-session reuse on shorter runs; that ceiling
disappears entirely under long sessions.

## Decision

`audit_v1_ui_matrix.py` MUST enforce a **two-layer time cap** with hard
runtime enforcement (not a soft warning):

1. **Per-cell cap = 600s.** Any single cell that exceeds 600s is
   aborted with reason `per_cell_cap_exceeded` and the run continues
   with the next cell.
2. **Per-session cap = 1800s.** When cumulative session duration
   (measured via `time.monotonic()` at run start) crosses 1800s, the
   current `browser.new_context()` is closed, a fresh context is
   created, and a fresh `login()` is performed. The remaining cells
   continue under the new context.

The 1800s value is below the canonical JWT expiry threshold (30min)
and well within Patroni leader rotation tolerance. The 600s value is
~3σ above the observed p95 cell duration during clean runs.

In combination with [[bfs-auth-race-window]] the splitter MUST wait
for `__wmahPageReady` after each fresh login so subsequent cells do
not race the session-restore code path.

## Consequences

- Long-session runs no longer crash en masse on JWT expiry.
- Per-cell cap absorbs unexpected hangs (`page.waitForSelector` long
  timeouts on missing landmarks) without poisoning later cells.
- Two-layer cap composes with `with_retry` (ADR-011 + svc-viability-v3
  C8, `apps/api/harness/core/db.py:with_retry`) on the backend so a
  Patroni transient drop during an audit_v1 run does not produce a
  spurious cell failure.
- `summary.json` MUST surface `cap_exceeded_cells` (count + reasons)
  so reviewers can distinguish environmental cap hits from real
  product defects.

## Alternatives considered

- **Token refresh interceptor (frontend-only fix).** Rejected because
  this is an audit script policy ADR, and the script must not depend
  on application code to compensate for its own session-reuse model.
  The interceptor can still be added orthogonally, but it is not the
  acceptance gate for this ADR.
- **Per-cell login (no session cap).** This is the dominant cost in
  audit_v1 run time (login p95 ≈ 1.5-2.0s × 112 ≈ 200s overhead).
  Acceptable in itself, but without an explicit per-session refresh
  policy the per-cell login becomes a "magic number" rather than a
  principled cap. The two-layer cap makes the policy explicit and
  enforceable in code.

## Follow-ups

- Implementation lands in svc-viability-v3 W3 atomic 4-file commit
  alongside A4 (per-cell login) + C8 (asyncpg with_retry).
- Memory rule [[long-session-playwright-cap]] to be authored after
  first production run that exercises the cap.
