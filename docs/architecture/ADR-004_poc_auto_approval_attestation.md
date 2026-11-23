# ADR-004 PoC_AUTO_APPROVAL Attestation Pattern

## Status
Accepted as a Stage 0.5 architecture contract. The pattern is engaged only in the PoC environment;
production builds dead-code-eliminate the auto-approval handler and any production request to the
auto-approval path returns `403 poc_auto_approval_denied_in_prod`. Authored 2026-05-17 under
RALPLAN-DR Iteration 2 Wave 1 Stage 0.5; source-of-truth REG-06 §3 / §5.

## Context
The PoC must demonstrate the recommendation/order simulation flow (BIZ-09 4-gate) end-to-end —
including BRANCH_MANAGER approval — without a real branch manager in the demo room. Without an
explicit governance pattern this becomes either (a) a hidden bypass that pretends a human approved,
or (b) a manual click-through that breaks the autopilot story. Both are unacceptable: (a) hides a
SoD violation; (b) renders the simulation lane unrunnable.

REG-06 §3 defines the `PoC_AUTO_APPROVAL` pattern: an action_code family + `gate_evidence_json`
schema + UI affordances that **make the absence of a human reviewer auditable rather than hidden**.
This ADR formalizes the attestation gating, the evidence schema, the operational limits, and the
production safety net.

## Drivers
- REG-06 §2 SOC2 SoD: automated decisions must record reviewer ≠ author or explicitly mark the
  reviewer as null with a governance marker; hiding a null reviewer behind a synthetic name is a
  SoC2 finding.
- REG-06 §5 Chaos Monkey opt-in pattern: dangerous self-service capabilities require multi-layer
  attestation, time-bounded windows, and abort criteria.
- AWS Sandbox OU pattern: production builds must compile-time exclude PoC-only code paths
  (preventive guardrail, not runtime).
- Stripe test-mode pattern: namespace separation between PoC and production secrets/identities so
  cross-contamination fails fast at boot.
- BIZ-09 4-gate: suitability, explanation duty, synthetic consent, employee approval — all four
  must record evidence; the auto-approval pattern automates only the fourth gate and only when the
  first three are PASSED.

## Decision

### 1. Three-Layer Attestation
Auto-approval activates only when **all three** of the following are simultaneously true at the
moment of the request:

| Layer | Source | Check | Failure mode |
|---|---|---|---|
| A — Build-time | `POC_AUTO_APPROVAL_ENABLED=true` env var | Resolved at server boot; immutable until process restart | Layer A false → fallback to human approval path; not an error |
| B — DB | `system_flags.demo_mode = true` row, UPDATE-guarded by trigger requiring ADMIN + `change_reason` + `ticket_id` | Read at request time (cached for ≤ 5s) | Layer B false → fallback to human approval path; not an error |
| C — Request | `X-Poc-Demo-Mode: 1` header on the request | Header presence is the SPA's environment self-identification (set by Vite build flag `IS_POC_BUILD`) | Layer C false → fallback to human approval path; not an error |

All three layers true → the request enters the auto-approval handler. Any single layer false →
the request goes through the normal human-approval flow (which in the PoC simply blocks pending a
BRANCH_MANAGER click; demo flows depend on Layer A+B+C being true).

Production builds **must** ship with Layer A absent (env var unset) and the auto-approval handler
dead-code-eliminated (see §"Dead-Code Elimination"). If a production-built artifact somehow
receives a request with Layer C header set, the production guard `if env != "poc"` rejects with
`403 poc_auto_approval_denied_in_prod` and emits an audit row of the same action_code.

### 2. `gate_evidence_json` Schema (audit_logs.detail_json subtree)
Every auto-approval audit row carries this canonical shape (REG-06 §3.2):

```json
{
  "governance_marker": "PoC_AUTO_APPROVAL",
  "demo_mode": true,
  "demo_mode_attested_by": "EMP_ADMIN_<uuid>",
  "environment": "poc-internet",
  "auto_approval_reason_code": "FOUR_GATES_PASSED_NO_HUMAN_REVIEWER",
  "four_gates": {
    "suitability_check": {
      "status": "PASSED|BLOCKED",
      "rule_id": "SUIT-<YYYY-NN>",
      "score": 0.0,
      "blocked_reason_code": null
    },
    "explanation_duty": {
      "status": "PASSED|BLOCKED",
      "doc_versions": ["<doc-id>:<version>"],
      "ack_at": "<ISO8601 UTC>",
      "blocked_reason_code": null
    },
    "synthetic_consent": {
      "status": "PASSED|BLOCKED",
      "consent_id": "SYN-C-<NNNN>",
      "synthetic": true,
      "blocked_reason_code": null
    },
    "employee_approval": {
      "status": "AUTO_APPROVED|HUMAN_APPROVED|BLOCKED",
      "approver_role": "PoC_AUTO_APPROVAL|BRANCH_MANAGER",
      "human_reviewer": null,
      "blocked_reason_code": null
    }
  },
  "blocked_reason_codes": [],
  "sod_warning": "human_reviewer=null; this transition is invalid in production",
  "prod_guard": {
    "would_block_in_prod": true,
    "guard_env_var": "POC_AUTO_APPROVAL_ENABLED"
  },
  "rate_limit_state": {
    "employee_id": "<uuid>",
    "per_minute_count": 0,
    "per_hour_count": 0,
    "ceiling_minute": 10,
    "ceiling_hour": 60
  }
}
```

**Invariants (enforced by `gate_evidence_v1` Pydantic model + DB JSONB CHECK where feasible):**

1. `governance_marker == "PoC_AUTO_APPROVAL"` and `demo_mode == true` are required for any row
   whose `action_code ∈ {recommendation_simulation_auto_approve,
   order_simulation_auto_approve, order_simulation_auto_execute_simulated}`.
2. If any `four_gates.*.status != "PASSED"` (excluding `employee_approval` which may be
   `AUTO_APPROVED`), the row's `action_code` **must** be `poc_auto_approval_blocked` with
   `blocked_reason_codes` populated from the closed set
   `{SUITABILITY_FAIL, EXPLANATION_FAIL, CONSENT_MISSING,
   EMPLOYEE_APPROVAL_REQUIRED_IN_PROD, ENV_MISMATCH}` (REG-06 T302 taxonomy).
3. `employee_approval.human_reviewer` non-null with `approver_role=BRANCH_MANAGER` **must** route
   to the normal `recommendation_simulation_approve` / `order_simulation_approve` action_codes —
   cross-talk between human and auto paths is forbidden.
4. `prod_guard.would_block_in_prod` is the fixed constant `true`. Code generators and tests
   assert this constant statically; any drift fails the validator.
5. The `rate_limit_state` block reflects post-decrement counters; the decision logic uses the
   pre-decrement values from Redis (see §"Operational Limits").

### 3. Action Code Family (OBS-02 canonical, REG-06 §3.1)
New action_codes (added via V022 in Stage 1 per plan §5):
- `recommendation_simulation_auto_approve` — 4-gate PASS + Layer A+B+C true.
- `order_simulation_auto_approve` — mock order auto-approved.
- `order_simulation_auto_execute_simulated` — mock execution completed.
- `poc_auto_approval_blocked` — gate fail or rate-limit / abort condition triggered.
- `poc_auto_approval_denied_in_prod` — fixed fail-closed if reached in production environment.
- `demo_mode_toggle_on`, `demo_mode_toggle_off` — Layer B transitions.
- `demo_mode_expiry_warning` — 5-minute pre-expiry alert (T312).

All seven codes carry `detail_json.governance_marker = "PoC_AUTO_APPROVAL"` so a single grep over
audit_logs isolates the PoC governance lane.

### 4. Operational Limits
- **Window**: `system_flags.demo_mode` activation has a hard expiry of **8 hours** from
  `toggled_on_at`. A batch hook (T312) fires `demo_mode_expiry_warning` 5 minutes before, then
  auto-toggles to false at expiry and emits `demo_mode_toggle_off` with reason
  `auto_expiry_8h_ceiling`.
- **Per-employee ceiling**: Redis-backed counter
  `harness:poc:auto_approve:rl:<employee_id>:<yyyymmddHHMM>` for per-minute (cap 10) and
  `harness:poc:auto_approve:rl:<employee_id>:<yyyymmddHH>` for per-hour (cap 60). Exceeding either
  cap returns `429` with `failure_reason_code=auto_approval_ceiling_exceeded` and the audit row
  `poc_auto_approval_blocked`.
- **Abort conditions (auto-OFF Layer B)**: a watcher (T313) evaluates over a 10-minute sliding
  window and toggles `demo_mode` to false when any of:
  - 4-gate fail-closed rate > **5%** of attempted auto-approvals (the plan tightens REG-06 §5's
    informational 30% to a stricter 5% — rationale: the PoC's flows are deterministic; >5% means a
    rule or seed regression rather than tail variance);
  - audit_logs append lag p99 > **60 seconds** (REG-06 §5 set 5s informational; this ADR uses 60s
    end-to-end pipeline lag for autopilot resilience while still failing-closed before SOC2
    finding territory);
  - global `/auth/*` or per-IP rate-limit breach rate > **5%** in window.
  Each auto-OFF emits `demo_mode_toggle_off` with detail_json
  `{reason: "abort_<condition>", metric_value: ..., threshold: ...}`.

### 5. Dead-Code Elimination in Production Build
- The frontend SPA build script (`pnpm build:prod`) sets `IS_POC_BUILD=false`. The conditional
  module containing the `X-Poc-Demo-Mode` header injector and the PoC-only UI badge component is
  guarded behind `if (import.meta.env.VITE_IS_POC_BUILD)` such that Vite's tree-shaker removes it
  from the production bundle. CI gate `scripts/check_no_poc_in_prod.sh` (T305) greps `dist/` for
  the literal string `PoC_AUTO_APPROVAL` and fails the build if found.
- The backend module structure splits auto-approval into
  `apps/api/harness/services/poc_auto_approval.py` which is imported by `routers/simulation.py`
  only when `os.getenv("POC_AUTO_APPROVAL_ENABLED") == "true"`. A static import guard plus a
  pre-import `prod_guard()` helper ensures any production-built artifact that nonetheless ships
  the module still fails closed at the first request with `403 poc_auto_approval_denied_in_prod`.
- A backstop ESLint rule (`no-poc-auto-approval-in-prod`) flags any reference to
  `PoC_AUTO_APPROVAL` outside files matching `**/poc/**` or `**/demo/**`.

### 6. UI Disclosure (REG-06 §3.3)
- Amber badge "PoC AUTO APPROVAL · 데모 모드" on every simulation card produced under this lane.
- Status chip "자동 승인됨 (검토자 없음)" adjacent to `SIMULATED_EXECUTED`.
- Detail-panel footer in Korean: "이 화면의 결재는 PoC 데모 환경에서 자동으로 승인됩니다. 실제
  주문/계좌 반영은 발생하지 않습니다."
- `data-poc-auto-approval="true"` attribute + matching aria-label; E2E regression (T308, T309)
  asserts presence.
- PDF/CSV exports carry a 60° watermark "POC SIMULATION — NOT A REAL ORDER" (T307).

## Alternatives Considered
- **Single env-var attestation**: rejected — environment variables can be accidentally inherited
  in production, and a single layer offers no defense in depth.
- **Two-layer (env + header)**: rejected — without the DB Layer B, every PoC server boot would
  silently auto-approve regardless of operator intent; Layer B provides the human-attested
  on/off control with ticket trail.
- **Synthetic BRANCH_MANAGER identity that fakes a human reviewer**: rejected — hides the SoD
  violation; SOC2 auditors flag this pattern explicitly. Recording `human_reviewer: null` with a
  governance marker is the honest path.
- **No abort criteria, manual toggle only**: rejected — REG-06 §5 chaos-abort pattern is mandatory
  for self-service capabilities; without auto-OFF a misfiring rule cascades silently.
- **8h window unbounded by per-employee ceiling**: rejected — REG-04 LLM10 unbounded-consumption
  posture extends to governance lanes: a runaway autopilot must hit a per-employee rate cap.

## Why Chosen
- The three-layer attestation maps cleanly onto three independent trust domains (build, ops, SPA),
  so a single compromise cannot enable production auto-approval.
- The fixed-constant `prod_guard.would_block_in_prod=true` is statically verifiable by the
  ADR-007 validator contract suite; no behavioral test required.
- The `gate_evidence_json` schema reuses BIZ-09's 4-gate model exactly, so the audit row's
  semantics are identical between auto-approved and human-approved paths — the only difference is
  `employee_approval.human_reviewer == null` plus the governance_marker.
- The dead-code elimination + production guard double-net mirrors the AWS Sandbox OU + SCP
  pattern (preventive at build time, fail-closed at runtime).

## Consequences
- V020 (`system_flags`), V021 (`governance_marker`), V022 (`action_code` enum expansion) become
  hard prerequisites for any simulation-lane PR after Stage 1.
- The Mailpit sandbox (ADR-002) and PoC_AUTO_APPROVAL share the same "PoC-only, fail-closed in
  prod" pattern — the same `prod_guard()` helper is reused.
- Operators must understand that toggling `demo_mode` is an audited admin action with an 8h
  ceiling, not an environment knob.
- The 5% / 60s / 5% abort thresholds are stricter than REG-06 §5 (which set 30% / 5s / 5%
  informational); this ADR's values supersede REG-06 informational figures and are revised only via
  ADR amendment.
- `scripts/generate_sod_evidence_pack.py` (ADR-007) consumes this schema as its primary input and
  produces the weekly SoD report for the demo audit narrative.

## Follow-ups
- T300 — `governance_marker` column + index (Stage 1 V021).
- T301 — `action_code` enum expansion (Stage 1 V022).
- T302 — Pydantic model `GateEvidenceV1` + JSON Schema export.
- T303 — `system_flags` + UPDATE trigger (Stage 1 V020).
- T304 — FastAPI dependency `poc_auto_approval_guard()` enforcing Layer A+B+C.
- T305 — CI gate `scripts/check_no_poc_in_prod.sh` greps `dist/` for `PoC_AUTO_APPROVAL`.
- T306 / T307 — UI badge + PDF/CSV watermark.
- T308 / T309 — 5-role × 14-scenario regression + Playwright E2E.
- T312 — 8h auto-expiry batch hook.
- T313 — abort-criteria watcher (4-gate fail rate, audit lag, rate-limit).
- T314 — per-employee ceiling rate-limit.

## Cross-References
- **BIZ-06 Compliance**: 4-gate definition and PB/WM/BRANCH_MANAGER role authority; PoC_AUTO_APPROVAL
  automates only gate 4 (employee_approval) and only when gates 1–3 are PASSED.
- **BIZ-09 Recommendation/Order Simulation**: the 4-gate machine this ADR governs.
- **SEC-01 Auth Spec**: ADMIN required for Layer B toggle; PB/WM are the actors whose ceilings are
  enforced.
- **AI-04 RAG Spec**: not in the auto-approval critical path, but ai_outputs surfaced inside
  simulation cards remain subject to ADR-005 quarantine flagging when surfaced.
- **REG-06 §3 / §5**: source-of-truth for this pattern; this ADR tightens the abort thresholds
  (5% / 60s / 5%) and pins the dead-code-elimination contract.
- **REG-04 §3-bis Excessive Agency (LLM06) / Unbounded Consumption (LLM10)**: per-employee
  ceiling implements LLM10 posture for governance lanes.
- **ADR-002 Email Authority**: shared `prod_guard()` helper for the "PoC-only path, fail-closed
  in prod" pattern.
- **ADR-005 Dual-LLM Quarantine**: simulation cards surfacing AI-generated rationale carry the
  `quarantined` flag; auto-approval does not waive the dual-LLM contract.
- **ADR-006 Audit Append-Only**: every PoC_AUTO_APPROVAL audit row inherits V008+V019 append-only
  invariants.
- **ADR-007 Validator Contracts**: `generate_sod_evidence_pack.py` consumes the
  `gate_evidence_json` shape defined here.
