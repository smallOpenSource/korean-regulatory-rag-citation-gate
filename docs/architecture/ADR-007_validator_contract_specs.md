# ADR-007 Validator Contract Specs (Four New Validator Scripts)

## Status
Accepted as a Stage 0.5 architecture contract. Defines the input flags, behavior, exit-code
taxonomy, output JSON shape, and degraded-reason taxonomy for four validator scripts that
execute across Stages 3, 5, 6, and 8. Authored 2026-05-17 under RALPLAN-DR Iteration 2 Wave 1
Stage 0.5 (P-7); the contract spec is authored **before** Stage 1 so that workers in Stages 1–7
emit compatible evidence as they go. Source-of-truth `.omc/plans/ralplan-wmah-final-completion.md`
§5 Stage 0.5 action 8.

## Context
Four validator scripts gate the PoC's acceptance evidence and must produce machine-readable
output that downstream scripts and human reviewers can consume identically. Without a
pre-committed contract:
- Stage 3's `external_dependency_attestation.py` and Stage 8's
  `verify_external_research_application.py` would emit ad-hoc shapes that complicate the
  `result.json` cross-references between specs and BACKLOG.
- Stage 5's seven-principles report and Stage 6's SoD evidence pack would require post-hoc
  parsing alignment work.
- The "degraded" classification for live-dependency checks would creep into "failed" or vice
  versa, eroding the meaning of pass/fail.

This ADR fixes the cross-cutting conventions and per-script contracts.

## Drivers
- P-3 / P-7 from RALPLAN-DR Iteration 2: validator contracts must precede stage execution so
  evidence shape is stable.
- REG-06 §5 chaos-abort posture: degraded ≠ failed; degraded means a pre-approved reason from a
  closed set, anything else is failed.
- REG-04 §3-bis Audit Backbone: token consumption is itself an audit metric; the external-
  dependency validator owns the per-Azure-call accounting.
- Operational reality of live external dependencies: off-hours, quotas, holidays, and provider
  outages will happen during a 30-day acceptance window — the validator must distinguish them
  from genuine integration regressions.

## Decision

### 0. Cross-Cutting Conventions
All four validators share the following invariants:

1. **Top-level JSON keys**: every output JSON has at least
   `{verified_at: <ISO8601 UTC>, status: "passed|degraded|failed", passed: <bool>}` at the root.
   `passed=true` iff `status ∈ {"passed", "degraded"}` (degraded with a pre-approved reason is
   still "passed" for gate purposes).
2. **`evidence_paths` array**: every output carries a top-level `evidence_paths: [<path>, ...]`
   listing the files written during the run (`.omx/reports/verification/...`).
3. **Exit code base set**: `0=passed`, `2=failed`, `3=config error` (missing env var, invalid
   window, malformed input file). Individual scripts may add codes (e.g., `4=token budget
   exhausted` for `external_dependency_attestation.py`).
4. **Output destination**: primary report at the `--out` path; sibling `.json` automatically
   written when the primary is `.md` and `--also-json` is passed (relevant for Stages 5 and 6).
5. **Time format**: ISO 8601 UTC with seconds precision and trailing `Z` (e.g.,
   `2026-05-17T09:12:03Z`).
6. **No fabrication**: if a check cannot run because of a config error, exit `3` and write
   `{status: "failed", passed: false, error: "<reason>"}` — do not synthesize a passing result.

### 1. `scripts/external_dependency_attestation.py` (Stage 3 owner)

**Purpose**: prove that each external dependency (Azure GPT5/mini per agent × 7, SMTP sandbox,
BROKER live quote, Data.go.kr 국채, PYKRX/FDR cross-check) was actually called within an
acceptance window. **No mocks, ever** — uses the real client classes.

**Inputs (CLI flags)**:
- `--window-start <ISO8601 UTC>` — default: `now() - 24h`.
- `--window-end <ISO8601 UTC>` — default: `now()`.
- `--allow-degraded <comma-separated>` — subset of `{azure, smtp, broker, data_go_kr, pykrx_fdr}`;
  user-pre-approved dependencies that may degrade rather than fail. Default: empty (any degrade
  is failed unless reason is in the closed-set taxonomy).
- `--out <path>` — default
  `.omx/reports/verification/external-dependency-attestation-<UTCstamp>.json`.
- `--env-profile {poc,acceptance,demo}` — selects the recipient/symbol fixture set.

**Behavior**:
- Runs one **live** call per dependency:
  - Azure GPT5/mini: one minimal-payload call per agent (rag_qa, email_draft,
    consultation_briefing, house_view_generation, nba_script, compliance_check,
    portfolio_analysis), 7 calls total.
  - SMTP sandbox: one synthetic `@example.invalid` recipient send via Mailpit; verify capture
    via Mailpit API.
  - BROKER live quote: one `005930` (Samsung Electronics) quote during KRX office hours; off-hours
    → `BROKER_OFFICE_HOURS_OFF` degraded.
  - Data.go.kr 국채: one bond quote; quota or 5xx → degraded with the matching reason.
  - PYKRX/FDR cross-check: one same-day delta-bp comparison; holiday → degraded.
- Persists each call's evidence to `evidence_paths` and increments the token-consumption metric
  for Azure calls.
- A dependency is `passed` if the live call returned valid data; `degraded` if it failed for a
  reason in the closed-set taxonomy below; `failed` for any other reason.

**Exit codes**:
- `0` — all 5 deps satisfied (passed, or honestly degraded with a pre-approved closed-set reason).
- `2` — one or more deps failed (unexpected error, or degraded with a reason outside the closed
  set, or degraded without `--allow-degraded` permission).
- `3` — config error (missing env, invalid window).
- `4` — token-budget exhaustion (per-window Azure token cap hit; see §"Token Consumption Metric").

**Output JSON shape**:
```json
{
  "status": "passed|degraded|failed",
  "passed": true,
  "verified_at": "<UTC>",
  "window": {"start": "<UTC>", "end": "<UTC>"},
  "env_profile": "poc",
  "deps": {
    "azure_gpt5_mini": {
      "status": "passed|degraded|failed",
      "agent_calls": [
        {
          "agent": "rag_qa",
          "model": "gpt5-mini",
          "latency_ms": 812,
          "tokens_in": 1245,
          "tokens_out": 280,
          "evidence_id": "<uuid>"
        }
      ],
      "degraded_reason": null
    },
    "smtp_sandbox": {
      "status": "passed",
      "transport": "mailpit",
      "message_id": "<id>",
      "recipient": "syn-pb-01@example.invalid",
      "degraded_reason": null
    },
    "broker_live_quote": {
      "status": "passed|degraded",
      "symbol": "005930",
      "price": 71500,
      "as_of": "<UTC>",
      "degraded_reason": null
    },
    "data_go_kr_bond_live": {
      "status": "passed|degraded",
      "bond_id": "...",
      "as_of": "<UTC>",
      "degraded_reason": null
    },
    "pykrx_fdr_cross_check": {
      "status": "passed|degraded",
      "day": "2026-05-16",
      "delta_bp": 0.3,
      "degraded_reason": null
    }
  },
  "token_consumption": {
    "azure_tokens_in": 8715,
    "azure_tokens_out": 1960,
    "azure_cost_usd_est": 0.024,
    "ceiling_remaining": 91285
  },
  "evidence_paths": [".omx/reports/verification/<files>"]
}
```

**Degraded-reason taxonomy (closed set; any other reason → `failed`)**:

| code | meaning |
|---|---|
| `BROKER_OFFICE_HOURS_OFF` | 영업외 시각 — KRX session closed |
| `DATA_GO_KR_QUOTA_EXHAUSTED` | 일일 호출 한도 초과 |
| `DATA_GO_KR_5XX_TRANSIENT` | 3회 재시도 후도 5xx 응답 |
| `PYKRX_FDR_HOLIDAY` | 영업일 아님 (휴장일) |
| `SMTP_SANDBOX_BOOT_TIMEOUT` | Mailpit 컨테이너 부팅 실패, 1회 재시도 후 |
| `AZURE_RATE_LIMIT_THROTTLED_LATE_WINDOW` | acceptance window 막판 429, 다음 데모 윈도우로 재시도 |
| `PROVIDER_WINDOW_UNAVAILABLE` | 사용자 사전 승인된 광범위 외부 장애 (user-approved override) |

**Token consumption metric**: every Azure call increments a per-agent counter persisted in
`audit_logs.detail_json.token_consumption`; a cumulative cap (configured via env
`AZURE_TOKEN_CEILING_PER_WINDOW`, default 100000 input + 20000 output) is enforced; reaching the
cap mid-run exits `4` with a partial-result JSON that still satisfies the cross-cutting top-level
keys.

### 2. `scripts/generate_seven_principles_report.py` (Stage 5 owner)

**Purpose**: produce a Markdown + JSON report scoring each of the 7 AI agents against the
metaprinciples codified in REG-04 (faithfulness / citation integrity / determinism / role
boundaries / fail-closed coverage / etc.). This becomes the "보조수단성" evidence for demo
review.

**Inputs**:
- `--ai-output-since <ISO8601 UTC>` — start of the evaluation window.
- `--out <path>` — default
  `.omx/reports/verification/seven-principles-report-<UTCstamp>.md`.
- `--also-json` — emit sibling `.json` at the same stem.

**Behavior**: aggregates rows from `ai_outputs`, `rag_answer_evidence`, `audit_logs` since the
window start; computes scores per (principle, agent) pair; emits one Markdown table + one
machine-readable JSON.

**Exit codes**:
- `0` — all 7 principles × 7 agents passed minimum threshold; report written.
- `2` — any principle fails minimum threshold (per-agent floor configured in
  `docs/ai/AI-06_nist_mapping.md` once T270 lands; default floor 0.7 faithfulness, 100% citation
  presence for rag_qa, 100% deterministic-field presence for golden snapshots).
- `3` — insufficient evidence rows (< 10 rag_qa outputs / < 5 per other agent in window).

**Output JSON shape**:
```json
{
  "status": "passed|failed",
  "passed": true,
  "verified_at": "<UTC>",
  "window": {"since": "<UTC>"},
  "principles": {
    "거버넌스":     {"rag_qa": {"score": 0.92, "evidence_path": "..."}, "...": "..."},
    "합법성":       {"...": "..."},
    "보조수단성":   {"...": "..."},
    "신뢰성":       {"...": "..."},
    "금융안정성":   {"...": "..."},
    "신의성실":     {"...": "..."},
    "보안성":       {"...": "..."}
  },
  "agent_summary": {
    "rag_qa":                  {"overall": 0.91, "weakest_principle": "보안성"},
    "email_draft":             {"...": "..."},
    "consultation_briefing":   {"...": "..."},
    "house_view_generation":   {"...": "..."},
    "nba_script":              {"...": "..."},
    "compliance_check":        {"...": "..."},
    "portfolio_analysis":      {"...": "..."}
  },
  "evidence_paths": [".omx/reports/verification/..."]
}
```

### 3. `scripts/generate_sod_evidence_pack.py` (Stage 6 owner)

**Purpose**: produce the SoD (Segregation of Duties) evidence pack used by SOC2-style review.
It must surface both legitimate auto-approval rows (where the absence of a human reviewer is
declared via `governance_marker=PoC_AUTO_APPROVAL`) and any rule violations (rows where a
human-required action_code has `human_reviewer IS NULL` outside the PoC_AUTO_APPROVAL governance
marker).

**Inputs**:
- `--from <ISO8601 UTC>` — window start.
- `--to <ISO8601 UTC>` — window end.
- `--out <path>` — default
  `.omx/reports/verification/sod-evidence-pack-<UTCstamp>.md` + sibling `.json`.

**Behavior**: queries `audit_logs` for the window; partitions rows into three buckets:
- **Bucket A** — `governance_marker = 'PoC_AUTO_APPROVAL'` (expected non-zero in PoC demo runs).
- **Bucket B** — `governance_marker IS NULL` AND `action_code` requires a human reviewer AND
  `human_reviewer IS NOT NULL` (the normal case; expected populated).
- **Bucket C** — `governance_marker IS NULL` AND `action_code` requires a human reviewer AND
  `human_reviewer IS NULL` (**violation**; expected zero or a user-approved exception list).

The set of "action_codes that require a human reviewer" is sourced from
`docs/observability/OBS-02_audit_action_codes.md` (the `human_reviewer_required` column once it
exists; until then a hardcoded list maintained inside the script with a comment pointing back
to OBS-02).

**Exit codes**:
- `0` — Bucket C is empty (or contained only entries from the `--allow-exception` CSV).
- `2` — Bucket C non-empty and not fully covered by the exception list.
- `3` — config error.

**Output JSON shape**:
```json
{
  "status": "passed|failed",
  "passed": true,
  "verified_at": "<UTC>",
  "window": {"from": "<UTC>", "to": "<UTC>"},
  "buckets": {
    "poc_auto_approval": {"count": 42, "sample_audit_ids": ["...", "..."]},
    "human_approved":    {"count": 18, "sample_audit_ids": ["...", "..."]},
    "violations":        {"count": 0,  "audit_ids": []}
  },
  "exception_list": [],
  "evidence_paths": [".omx/reports/verification/..."]
}
```

### 4. `scripts/verify_external_research_application.py` (Stage 8 owner)

**Purpose**: prove that every REG-01..06 §5/§6 task ID maps onto a BACKLOG entry + audit_code
(when REG demands) + UI screenshot evidence (when REG demands) + golden test (when REG demands).

**Inputs**:
- `--backlog <path>` — default `BACKLOG.md`.
- `--regs <dir>` — default `docs/regulations/`.
- `--audit-codes-doc <path>` — default
  `docs/observability/OBS-02_audit_action_codes.md`.
- `--ui-evidence <dir>` — default `apps/web/playwright-report/`.
- `--out <path>` — default
  `.omc/specs/autoresearch-external-research-application/result.json`.

**Behavior**: parses each REG-NN file's §5 / §6 sections for task IDs; cross-references against
the BACKLOG; for each REG row that declares an audit-code requirement, asserts the code exists
in OBS-02; for each row that declares UI evidence, asserts a matching screenshot exists; for
each row that declares a golden test, asserts a matching test file exists.

**Exit codes**:
- `0` — every REG-NN §5/§6 task ID maps to a BACKLOG entry and to the required artifacts.
- `2` — any traceability miss (one or more rows unmapped).
- `3` — config error (missing input file/dir).

**Output JSON shape**:
```json
{
  "status": "passed|failed",
  "passed": true,
  "verified_at": "<UTC>",
  "summary": {
    "reg_rows_total": 0,
    "backlog_matches": 0,
    "audit_code_matches": 0,
    "ui_evidence_matches": 0,
    "golden_test_matches": 0,
    "unmapped": []
  },
  "by_regulation": {
    "REG-01": {"...": "..."},
    "REG-02": {"...": "..."},
    "REG-03": {"...": "..."},
    "REG-04": {"...": "..."},
    "REG-05": {"...": "..."},
    "REG-06": {"...": "..."}
  },
  "evidence_paths": [".omc/specs/autoresearch-external-research-application/..."]
}
```

## §4 Measurement Collection Cadence

This section amends ADR-007 to codify how runtime measurement data is collected, validated for
freshness, and enforced as a gate condition. Authored 2026-05-18 under UltraQA Cycle 2
Workstream C (AC10).

### §4.1 Collector Cron Cadence

Measurement collectors run on the following schedule (configurable via env vars):

| Collector | Default cadence | Env var override |
|---|---|---|
| Faithfulness / citation presence (rag_qa) | Every 1 hour | `MEASUREMENT_CRON_FAITHFULNESS` |
| Golden snapshot stability (all agents) | Every 24 hours | `MEASUREMENT_CRON_GOLDEN_STABILITY` |
| Quarantine score distribution | Every 1 hour | `MEASUREMENT_CRON_QUARANTINE` |
| Token consumption per window | Every 1 hour | `MEASUREMENT_CRON_TOKEN` |
| Leakage Jaccard distribution | Every 24 hours | `MEASUREMENT_CRON_LEAKAGE` |

Each collector writes a sidecar JSON file at the path declared in the corresponding
`evidence_anchor` field of the `[PENDING_MEASUREMENT:...]` marker or citation in AI-06.

### §4.2 Freshness Window

The default freshness window is **7 days** (`MEASUREMENT_FRESHNESS_WINDOW_DAYS`, default `7`).
A measurement JSON is considered fresh if either:
- Its `last_measured_at` field (ISO 8601 UTC) is within the freshness window, OR
- Its file mtime is within the freshness window (fallback when `last_measured_at` is absent).

Stale measurements are treated identically to missing measurements for gate purposes.

### §4.3 Stale Handling — Fail-Closed

When `scripts/audit_ai06_measurement_freshness.py` detects a stale or missing citation:
- The script exits `1` and emits a `STALE` or `MISSING` diagnostic to stderr.
- The composite acceptance gate (`scripts/run_verification_gate.sh`) treats exit `1` from this
  script as a **gate FAIL** — the acceptance window cannot close while stale measurements exist.
- There is no "degraded" classification for stale measurements; stale = failed.

### §4.4 PENDING_MEASUREMENT Maximum Age

A `[PENDING_MEASUREMENT:...]` marker may remain in documentation for at most **30 days** from the
`deadline` field (`PENDING_MEASUREMENT_MAX_AGE_DAYS`, default `30`).

`scripts/check_pending_measurements.py` exits `1` if any `deadline` field is in the past.
This means a marker whose deadline has passed is treated as an expired obligation, not an
acceptable placeholder. The owning team must either:
1. Replace the marker with a live citation (measurement collected), OR
2. Obtain an explicit extension (update the `deadline` field with sign-off commit message).

### §4.5 Measurement JSON Schema

Every measurement sidecar JSON produced by a collector must conform to the following schema
(ADR-007.1 sidecar schema):

```json
{
  "principle_id":        "<string — e.g. MS-1.1, MS-2.7>",
  "metric":              "<string — human-readable metric name>",
  "value":               "<number — point-in-time measured value>",
  "p95":                 "<number | null — 95th-percentile value if applicable>",
  "sample_n":            "<integer — number of samples in the measurement window>",
  "denominator_source":  "<string — table/query/script that produced the denominator>",
  "denominator":         "<integer | null — total population used to compute value>",
  "last_measured_at":    "<ISO 8601 UTC string, e.g. 2026-05-18T12:00:00Z>",
  "expires_at":          "<ISO 8601 UTC string — last_measured_at + freshness window>",
  "source_path":         "<string — relative path to this JSON file from project root>"
}
```

Required fields: `principle_id`, `metric`, `value`, `sample_n`, `last_measured_at`,
`expires_at`, `source_path`. Optional: `p95`, `denominator_source`, `denominator`.

Collectors that omit required fields produce an invalid sidecar; `audit_ai06_measurement_freshness.py`
treats an invalid or unparseable JSON as a missing measurement (exit 1).

## Alternatives Considered
- **One uber-script that runs all four checks**: rejected — Stage owners differ; bundling
  delays Stage 3 evidence behind Stage 8 readiness; modular scripts let each Stage run its
  own gate.
- **Free-form output**: rejected — without the cross-cutting top-level keys, downstream
  result.json aggregation (autoresearch-total-product-readiness, §11 of the plan) cannot be
  built incrementally.
- **Open-ended degraded-reason set for Script 1**: rejected — REG-06 §5 chaos-abort posture
  requires "degraded" to mean exactly one of a small set of pre-approved reasons. Open-ended
  reasons let real failures masquerade as expected degrades.
- **Mocks for external dependencies in Script 1**: rejected explicitly — the script's purpose is
  to attest real provider availability. Mocks would invalidate the entire artifact.
- **Including hash-chain integrity in Script 3**: rejected for v1 — the audit hash chain is not
  yet implemented; including it now would require either skipping (lying) or pre-implementing
  hash chain (scope creep). When introduced (separate ADR), this script will gain a new bucket.

## Why Chosen
- The cross-cutting `{verified_at, status, passed}` + `evidence_paths` triple lets a downstream
  spec aggregator (autoresearch-total-product-readiness/result.json) consume all four scripts
  with a single parser.
- The closed-set degraded-reason taxonomy for Script 1 makes pass/fail meaningful under
  predictable external-world conditions (KRX office hours, holidays, quotas) while preserving
  the failure signal for actual regressions.
- Token consumption tracked in Script 1 is the foundation for ADR-005's per-agent budget
  enforcement and for the seven-principles report's "보안성" / "신뢰성" scoring.
- The four scripts are pre-contracted across Stages, so Stage 1 (Wave 1) workers begin emitting
  evidence in the right shape before Stage 3 begins — avoiding rework when validators arrive.

## Consequences
- All four validators must be reviewed by `architect` + `test-engineer` agents before Stage 3
  starts emitting evidence (plan §5 Stage 0.5 gate).
- The output schemas are part of the public contract — changes require an ADR-007 amendment.
- The `evidence_paths` directory `.omx/reports/verification/` becomes the canonical reports
  location; runbooks and dashboards point there.
- The cost ceiling on Azure tokens (Script 1 exit code 4) is a real operational guardrail —
  the acceptance window can be exhausted mid-run if a regression spikes token usage; this
  surfaces immediately rather than silently doubling the bill.
- The seven principles labels are Korean by design; non-Korean readers consume the JSON
  `agent_summary` instead.

## Follow-ups
- T-validator-3 — implement `external_dependency_attestation.py` per this contract (Stage 3).
- T-validator-5 — implement `generate_seven_principles_report.py` per this contract (Stage 5).
- T-validator-6 — implement `generate_sod_evidence_pack.py` per this contract (Stage 6).
- T-validator-8 — implement `verify_external_research_application.py` per this contract
  (Stage 8).
- T270 — `docs/ai/AI-06_nist_mapping.md` so Script 2's per-principle floor is documented.
- Stage 1 work must emit `audit_logs.detail_json.token_consumption` (Script 1) and
  `audit_logs.governance_marker` (Script 3) compatibly from day one.

## Cross-References
- **BIZ-06 Compliance**: provides the human-reviewer-required action_code taxonomy that Script 3
  consumes.
- **SEC-01 Auth Spec**: role separation determines who can run each validator (typically
  `harness_admin` or a dedicated `harness_validator` role; PoC uses admin).
- **AI-04 RAG Spec**: per-principle scoring inputs (faithfulness, citation integrity) flow into
  Script 2; closed-set `fail_closed_reason_code` from ADR-005 surfaces in Script 2's
  "신뢰성" / "보안성" rows.
- **ADR-001 WebSocket**: not in scope for these validators directly; WS contract is validated
  by `scripts/verify_websocket_contract.py` (separate plan §5 Stage 0.5 deliverable).
- **ADR-002 Email**: Mailpit sandbox is the SMTP dep in Script 1; the email state machine is
  validated by `scripts/verify_email_contract.py` (separate).
- **ADR-003 Dependency Gate**: any new dependency consumed by these scripts (DeepEval for
  Script 2, slowapi token-bucket for Script 1's retry shaping) is pre-approved in ADR-003 §3;
  additions require ADR-003 amendment.
- **ADR-004 PoC_AUTO_APPROVAL**: Script 3 consumes the `gate_evidence_json` shape defined in
  ADR-004; the governance_marker invariant is its primary signal.
- **ADR-005 Dual-LLM Quarantine**: token consumption and faithfulness scores tracked in
  Script 1 / Script 2 are the operational metrics for ADR-005's posture.
- **ADR-006 Audit Append-Only**: all three of Scripts 2/3/4 read `audit_logs`; the V008+V019
  append-only invariant makes their outputs trustworthy.
- **REG-04 §3 / REG-06 §5 / §11 of the plan**: source-of-truth.
