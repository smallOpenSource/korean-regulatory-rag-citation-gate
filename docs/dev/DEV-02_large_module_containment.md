# DEV-02 Large Module Containment

## Purpose
Large files already exist in the PoC because provider readiness, batch orchestration, and integration
contracts evolved quickly. This guide contains them without forcing a risky broad refactor during
feature delivery. New work must avoid making these files larger unless the task explicitly owns the
module and includes regression evidence.

## Rules
- Preferred target: keep new modules under 300 lines.
- Hard review threshold: 500 lines for Python/TypeScript/source test files.
- If a file over 500 lines must change, keep the diff narrow and document why extraction is unsafe
  in the commit body or task report.
- Split by existing seams first: provider client/parser, repository SQL, service payload builder,
  CLI argument parsing, report writer, and tests by behavior area.
- Do not introduce new dependencies to split large modules; use existing Python/TypeScript modules.
- Raw SQL extraction must preserve leading `/* sql_id: ... */` comments and repository-only DB access.

## Current Containment Register
The architecture validator scans for source files over 500 lines and requires each path here.

| path | current containment boundary | preferred next split |
|---|---|---|
| `apps/api/harness/batch/runner.py` | batch orchestration, postconditions, provider stage wiring | extract report/postcondition builders after behavior tests are stable |
| `apps/api/harness/batch/providers.py` | provider contracts, parsers, live-client adapters | split official-provider clients and pure parsers by source |
| `apps/api/harness/repositories/batch.py` | raw SQL constants and batch repository helpers | group read-only status SQL separately from write SQL |
| `apps/api/harness/services/readiness.py` | readiness payload composition and status derivation | split domestic-market/top200 builders from generic readiness |
| `tests/test_task2_batch_provider_lane.py` | provider-lane regression tests | divide provider policy, parser, and report assertions |
| `tests/test_batch_runner.py` | runner CLI/report regression tests | split CLI contract and postcondition report tests |
| `scripts/verify_serviceable_readiness.py` | canonical serviceable readiness validator | extract pure payload validators from CLI plumbing |
| `scripts/run_serviceable_canonical_readiness.py` | canonical evidence producer orchestration | split artifact path resolution from subprocess orchestration |
| `tests/test_backend_api_contracts.py` | backend contract/service regression tests | split route surface, SQL contract, and readiness service tests |
| `tests/test_api_boundary_harness.py` | local API boundary integration harness | split role matrix, malformed input, and fail-closed AI cases |
| `tests/test_four_gate_compliance.py` | 4-gate compliance regression suite (W2-T10) | split suitability/explanation/unfair-solicitation/marketing assertions per gate |
| `tests/test_seven_agents_golden.py` | 7-agent golden snapshot suite (W2-T11, REG-04 T261) | split per-agent JSON-schema regression into its own file once a new agent type lands |
| `tests/test_poc_auto_approval_matrix.py` | 5-role × 14-scenario PoC_AUTO_APPROVAL matrix (W2-T12) | split role-permission rows from gate-failure rows once scenario count grows past 20 |
| `apps/api/harness/services/poc_auto_approval.py` | 3-layer attestation guard + rate ceiling + abort + governance sweep (W2-T13) | extract rate-limit primitives and abort-evaluator after Wave 5 governance lands |
| `apps/api/harness/api/routers/email.py` | email lifecycle routes + marketing review gate + Mailpit transport (W2-T3) | split marketing-review endpoints from draft state-machine endpoints when AI compliance_check grows |
| `apps/api/harness/batch/scheduler.py` | APScheduler stub + env-driven cron config + `--run-once` CLI + provider job wiring (W3-T5) | split CLI argument parsing from scheduler daemon mode after Wave 5 governance lands |
| `apps/api/harness/batch/types.py` | Shared types/constants/utils for batch package (W3-T4 runner split) — pure, no I/O, no LOC cap | no-cap (single-responsibility data module); revisit only if cross-package types accumulate |
| `scripts/external_dependency_attestation.py` | ADR-007 §1 contract validator — Azure×7 + SMTP + BROKER + DATA_GO_KR + PYKRX/FDR + ECOS live attestation (W3-T5) | split per-provider attestation modules once the script grows beyond 700 lines |
| `scripts/verify_total_product_readiness.py` | ADR-007 aggregator — gate report + serviceable result + false-green controls + migrations + split diff + ext-dep + SoD + gitleaks + REG audit codes + DEV docs (W5-T2) | split per-domain component validators (gate, infra, docs) once aggregator exceeds 900 lines |
| `tests/test_poc_demo_governance.py` | W5-T1 integration suite — SoD evidence pack, poc-to-prod migration check, 5-role × 14-scenario governance matrix (W5-T1, worker-xray) | split SoD, migration check, and role-scenario matrix into separate files once scenario count exceeds 20 per category |
| `tests/test_rag_golden.py` | 10 RAG golden Q&A regression + adversarial + DeepEval hook + REG_PAGE/MANUAL seed fixture (W2-T11 + DI-2 seed) | extract `_seed_rag_test_chunks()` into a separate fixture module once additional agents need similar seed |
| `apps/api/harness/api/routers/ai.py` | AI job + AI output + RAG /rag/query+/rag/qa routes with injection pre-check, content safety toggle, dual-LLM Azure path, LLM07/LLM10 redactor + token meter, fail_closed_reason_code taxonomy + persistence (W2-T1 + W3-T6 + DI-2 patches) | split RAG generation path from job/output read routes once Azure generative dual-LLM lands as its own module |
| `apps/api/harness/api/routers/nba.py` | NBA cards + aftercare events + quarterly queue + status mutations + WS broadcast emit (T17/T243/T244/T257 + A.22 silent-except removal + Z5 B.2 @idempotent on PATCH /nba-actions/{id}/status) | split per-action-status PATCH path from aftercare-event lifecycle when the third concurrent maintenance touch lands |
| `scripts/v8_bfs_visitor.py` | v8 state-graph BFS DOM traversal — visitor + cell index + per-cell snapshot + emit unreachable/visited.jsonl (ADR-009 cycle harness) | split visitor traversal from snapshot serialisation when a second traversal strategy lands |
| `scripts/v8_calibration_generator.py` | v8 L1–L5 calibration label set generator + adversarial split + seed reproducibility (ADR-009 calibration harness) | split L1 generator from L2/L5 generators once any single layer's heuristic surface doubles |
| `apps/web/src/pages/HouseViewDetailPage.tsx` | house-view detail page — header/status/section panels + AI-output rendering + activation handoff (svc-quality register sync 2026-05-31) | split section panels and activation-handoff UI into child components when a second house-view layout lands |
| `scripts/audit_v1_workflow_e2e.py` | audit_v1 end-to-end workflow audit script (svc-quality register sync 2026-05-31) | split per-domain workflow probes from the shared driver once a second audit cycle reuses it |
| `scripts/audit_v1_ui_matrix.py` | audit_v1 UI route×role matrix audit script (svc-quality register sync 2026-05-31) | extract the route/role matrix data from the traversal driver |
| `scripts/audit_v1_copy_pb_perspective.py` | audit_v1 PB-perspective copy/wording audit script (svc-quality register sync 2026-05-31) | extract phrase detectors from the page-walk driver |
| `tests/test_service_consultation_briefing.py` | service-layer consultation briefing regression tests (svc-quality register sync 2026-05-31) | split job-lifecycle assertions from briefing-content assertions |
| `tests/test_house_view_active_status_unification.py` | house-view ACTIVE/ACTIVATED status unification regression tests (svc-quality register sync 2026-05-31) | split status-transition cases from activation-audit cases |

## Stop Conditions
- A new over-500-line source file fails the architecture validator until it is either split or added
  to this register with a concrete containment boundary.
- A touched large file must be verified with its nearest targeted tests before claiming completion.
- Broad deslop/refactor work should use a separate cleanup plan and regression tests before edits.

---

## Targeted splits (2026-05-17 RALPLAN-DR Iteration 2)

Authored under RALPLAN-DR Iteration 2 Wave 1 Stage 0.5 (P-9). This section binds the
four highest-risk modules to specific sub-module layouts with line-of-code budgets and
import-dependency maps. Source-of-truth `.omc/plans/ralplan-wmah-final-completion.md`
§5 Stage 0.5 action 7.

### Re-verified line counts (2026-05-17, `wc -l`)

| Source module | Lines (verified `wc -l`) | Plan-advisory | Δ |
|---|---:|---:|---:|
| `apps/api/harness/batch/runner.py` | **2305** | 2305 | 0 |
| `apps/api/harness/batch/providers.py` | **1902** | 1902 | 0 |
| `apps/api/harness/repositories/batch.py` | **1014** | 1014 | 0 |
| `apps/api/harness/services/readiness.py` | **1003** | 1003 | 0 |
| **Total** | **6224** | 6224 | 0 |

Line counts confirmed at the time of authoring; revalidate via `wc -l` on Stage-3 entry.

### Target sub-modules (≤ 500 lines each; ≤ 300 recommended) and dependency maps

| Source module | Lines now | Target sub-modules (≤ 500 lines each; ≤ 300 recommended) | Dependency map |
|---|---:|---|---|
| ~~`apps/api/harness/batch/runner.py`~~ → submodules | 2305 → split ✅ | [x] `runner.py` (294 ln, entry + orchestration + re-exports) → [x] `runner_provider.py` (462 ln, provider lifecycle) → [x] `runner_transform.py` (77 ln, transform/embed) → [x] `runner_derived.py` (60 ln, derived/house-view) → [x] `runner_readiness.py` (479 ln, readiness + postconditions + result aggregation) → [x] `apps/api/harness/batch/types.py` (1181 ln, shared types/constants/utils — no line cap; intentionally large single-responsibility module) | all 5 submodules ≤ 500 ln; `apps/api/harness/batch/types.py` is pure (no I/O); W3-T4 completed 2026-05-17 |
| ~~`apps/api/harness/batch/providers.py`~~ → `batch/providers/` package | 1902 → split ✅ | [x] `providers/__init__.py` (308 ln, registry + base + re-export shim) → [x] `providers/krx.py` (499 ln, KRX parsers/helpers) → [x] `providers/krx_collector.py` (449 ln, KRX collectors) → [x] `providers/dart.py` (423 ln, OpenDART) → [x] `providers/ecos.py` (213 ln, ECOS) → [x] `providers/broker_data_go_kr.py` (148 ln, BROKER + data.go.kr) | `providers/__init__.py` re-export shim active; all 5 submodules ≤ 500 ln; W3-T3 completed 2026-05-17 |
| ~~`apps/api/harness/repositories/batch.py`~~ → `repositories/batch/` package | 1014 → split ✅ | [x] `batch_jobs.py` (222 ln) → [x] `batch_artifacts.py` (428 ln) → [x] `batch_readiness.py` (390 ln) → [x] `batch_quarantine.py` (70 ln, new Stage 3) | `__init__.py` re-export shim active; sql_id namespace `harness.batch.repo.*` preserved; W3-T2 completed 2026-05-17 |
| ~~`apps/api/harness/services/readiness.py`~~ → `services/readiness/` package | 1003 → split ✅ | [x] `services/readiness/core.py` (481 ln) → [x] `services/readiness/serviceable.py` (423 ln) → [x] `services/readiness/quarantine.py` (41 ln, new Stage 3) | `__init__.py` re-export shim active; W3-T1 completed 2026-05-17 |

### Stage-3 readiness gate (binding)

**No Stage 3 PR may introduce new code into any of the four source modules listed above.** New
functionality must land in the new sub-modules (or in `batch/types.py` for shared type
definitions). The Wave 3 leader rejects any PR that grows the four source modules instead of
using the new sub-modules; this is non-negotiable for Stage 3.

Operational implication: Stage 1 and Stage 2 workers may touch these files only for in-place
fixes that do not grow LOC (e.g., a bugfix that swaps a function call). Any feature work — even
a single new function — must perform the split first.

### Backward-compat shim policy

Each refactor may keep a backward-compat shim for **exactly one Stage** to avoid forcing
simultaneous edits across all callers:

- `apps/api/harness/batch/providers.py` may exist as a thin re-export shim for one Stage after
  the package layout lands. The shim's body is strictly `from .providers import *` (with the
  package layout `apps/api/harness/batch/providers/` being the real source). The shim file's
  presence and its single-line body are the only allowed deviation from the 500-line rule for
  one Stage.
- `apps/api/harness/services/readiness.py` follows the same pattern with respect to the
  `services/readiness/` package.
- `apps/api/harness/batch/runner.py` retains its name (no package conversion required); the
  shim concept does not apply — the original file is reduced to ≤ 300 lines of orchestration
  while peer modules carry the rest.
- `apps/api/harness/repositories/batch.py` may exist as a re-export shim for one Stage; the new
  repositories (`batch_jobs.py`, `batch_artifacts.py`, `batch_quarantine.py`) are the real
  source.

After one Stage, the shim file is deleted and all callers must import from the new locations.
A grep for the shim path in PR diffs at the end of the shim Stage is the deletion-gate
evidence; the Wave 3 leader retires the shim during the Stage close-out.

## 2-marker reconciliation for SYN-FAM personas

SYN-FAM personas carry two distinct governance markers that are additive, not redundant.

### SYN- prefix (customer_no)
- **Scope**: DB CHECK constraint V037 (`chk_customer_no_syn_prefix`), persisted in the `customer_no`
  column, machine-validated on every INSERT/UPDATE.
- **Purpose**: Data governance — prevents synthetic rows from being mistaken for real customer
  records at the database layer. The constraint fires regardless of application logic.
- **Lifecycle**: Permanent. Never stripped from the `customer_no` value.

### [교육용] prefix (customer_name)
- **Scope**: `customer_name` column, persisted at seed time, rendered at the UI/PB display layer.
- **Purpose**: PB-perspective self-check — ensures any PB viewing a customer record sees an
  unambiguous education/demo marker in the name field. Prevents confusion between synthetic
  training personas and real client names during live demonstrations or screen-share sessions.
- **Lifecycle**: Persisted server-side in the DB `customer_name` field; server-side rendering
  automatically propagates it to every UI surface without per-component logic.

### Why both are required simultaneously
| Layer | Marker | Validated by |
|---|---|---|
| Database integrity | `SYN-` prefix on `customer_no` | V037 CHECK constraint (automatic) |
| User cognition / PB display | `[교육용]` prefix on `customer_name` | Seed fixture + UI render |

Using only `SYN-` on `customer_no` satisfies machine validation but leaves `customer_name`
(the field PBs read first) without a human-visible signal. Using only `[교육용]` on
`customer_name` satisfies the display check but provides no DB-layer enforcement. Both together
close both gaps with zero overlap in responsibility.

### Implementation note
`[교육용]` is persisted directly in the `customer_name` column in the seed fixture
(`db/fixtures/seed_50_family_personas.sql`). No runtime transformation is needed — server-side
rendering picks it up automatically from the stored value. The `customer_no` `SYN-` prefix is
enforced independently by the V037 constraint and is not affected by `customer_name` content.

### Cross-references
- **ADR-003 Dependency Gate**: splits must not introduce new dependencies; reuse existing
  Python stdlib + asyncpg + redis.
- **ADR-005 Dual-LLM Quarantine**: motivates the new `batch_quarantine.py` repository and
  `readiness/quarantine.py` service modules that surface quarantine telemetry.
- **ADR-007 Validator Contracts**: `external_dependency_attestation.py` (Stage 3 owner) emits
  evidence rows that the new `batch_quarantine.py` and `readiness/quarantine.py` consume.
- **REG-04 §3-bis Audit Backbone**: every audit row emitted by the split modules must remain
  compatible with the V008+V019 append-only invariant (ADR-006).
- Plan §5 Stage 0.5 action 7 — source-of-truth for the split mandate.
- Plan §5 Stage 3 — the consumer of this section's gate.

### Updated stop-condition (supersedes the four rows in "Current Containment Register")

The four rows in the "Current Containment Register" table above that point at
`runner.py`/`providers.py`/`repositories/batch.py`/`services/readiness.py` are **superseded by
this Targeted-splits section** for Stage 3 and beyond. The "preferred next split" text in those
rows is informational from Stage 0.5 onward; the binding contract is the table in this section.
The architecture validator continues to scan and flag any of the four source modules that grow,
and the Wave 3 leader rejects such PRs.
