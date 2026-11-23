# API-04 Four-Gate Compliance Flow

## Status

Implemented (REG-02 T15 / REG-03 T242). Documented here in response to
service-viability audit v1 finding **F6** (`HP1.json` showed 4-gate ack 4
returning `404 "gate not found — run check first"` because the pre-check
sequence was implicit and undocumented).

## Gate Inventory

`apps/api/harness/services/four_gate.py::GATE_NAMES`:

| order | gate_name              | purpose                                                |
|:-----:|------------------------|--------------------------------------------------------|
| 1     | `suitability`          | REG-02 T220 / T228 — six-factor suitability + grade gate |
| 2     | `explanation`          | REG-02 T222 — leading-block explanation checklist      |
| 3     | `unfair_solicitation`  | REG-02 T223 — definitive-language / loss-guarantee / channel-switch detection |
| 4     | `marketing`            | REG-02 T224 / REG-03 T247 — 광고심의 leading-block + AI compliance |

Lifecycle per gate (consultation_gates table):

```
PENDING ──[pre-check OK]──► PASSED ──[ack call]──► ACKNOWLEDGED
        └──[pre-check BLOCK]──► BLOCKED
```

`GET /consultations/{id}/four-gate` always returns all four entries —
gates without a DB row default to `PENDING` per `aggregate_gate_result`
(`apps/api/harness/services/four_gate.py:45-60`).

## Pre-check → Ack Sequence

The `/four-gate/{gate_name}/acknowledge` endpoint requires a
**pre-existing gate row**; `suitability_repo.acknowledge_gate` returns
`None` and the router raises 404 ("gate not found — run check first")
if no row exists (`apps/api/harness/api/routers/consultation_gates.py:371-372`).

For each gate, the row is created by the corresponding pre-check call
**before** the acknowledge call. The pattern follows
`consultation_gates.py:69-87` (the suitability POST: load actor →
load consultation → load customer/product → run check → upsert_gate →
audit_log).

### 1. Suitability

```http
POST /consultations/{consultation_id}/suitability
Authorization: Bearer {PB|WM access token}
Content-Type: application/json
Idempotency-Key: {uuid}

{
  "product_id": "{uuid}",
  "investment_objective": "적극투자형",
  "financial_situation": { ... },
  "investment_experience": { ... },
  "loss_tolerance_pct": 20,
  "investment_horizon_months": 36,
  "investor_classification": "GENERAL",
  "age_bracket": "30s",
  "form_option_orders": { ... }
}

# Enum constraints (per suitability_assessments check constraints):
#   investment_objective     ∈ {안전형, 안정형, 위험중립형, 적극투자형, 공격투자형}
#   age_bracket              ∈ {20s, 30s, 40s, 50s, 60s, 70s+}
#   investor_classification  ∈ {GENERAL, PROFESSIONAL}
#   loss_tolerance_pct       ∈ [0, 100]

→ 201
{
  "assessment_id": "{uuid}",
  "gate_status": "PASSED" | "BLOCKED",
  "fail_reasons": [...],
  "customer_grade": "...",
  "product_grade": "...",
  "investor_classification": "GENERAL" | "ELDERLY" | ...,
  "gate_id": "{uuid}"
}
```

- Audit code: `suitability_confirmed` (PASSED) or `suitability_grade_block` (BLOCKED)
- Side effect: creates `consultation_gates` row with `gate_name=suitability`.
- Role: PB or WM only (`_require_consultation_staff`).

### 2. Explanation

```http
POST /consultations/{consultation_id}/explanation-confirm
Authorization: Bearer {PB|WM access token}
Content-Type: application/json
Idempotency-Key: {uuid}

{ "checked_item_ids": ["item-1", "item-2", ...] }

→ 200 { "gate_status": "PASSED", "gate_id": "{uuid}", "checked_count": N }
```

- Audit code: `explanation_confirmed`
- Side effect: creates `consultation_gates` row with `gate_name=explanation`.
- Static gate — always returns PASSED for any non-empty (or empty) list;
  the leading-block validation lives in `GET /consultations/{id}/explanation-checklist`.

### 3. Unfair Solicitation

```http
POST /consultations/{consultation_id}/unfair-solicitation-check
Authorization: Bearer {PB|WM access token}
Content-Type: application/json
Idempotency-Key: {uuid}

{
  "message_text": "...",
  "product_id": "{uuid?}",
  "solicited": true,
  "last_face_to_face_seconds_ago": null,
  "has_opt_in_audit": false
}

→ 200
{
  "gate_status": "PASSED" | "BLOCKED",
  "violations": [{"rule_id": "...", "severity": "...", "detail": "..."}],
  "gate_id": "{uuid}"
}
```

- Audit code on BLOCKED only: `unfair_solicitation_blocked`
- Side effect: creates `consultation_gates` row with `gate_name=unfair_solicitation`.
- Rule categories: `REGEX_DEFINITIVE_LANGUAGE`, `RISK_GRADE_OVER`,
  `OFFLINE_TO_ONLINE_WINDOW`, `LOSS_GUARANTEE`.

### 4. Marketing

The marketing gate is **cross-resource** — it is created by the
`/email-drafts/{draft_id}/submit` flow rather than by a dedicated
`/consultations/{id}/marketing-check` endpoint. When a draft is
submitted with `marketing_classified=true`:

1. `services/marketing/core.run_marketing_gate` runs static lint + AI compliance.
2. `marketing_reviews` row is inserted with the decision.
3. The corresponding `consultation_gates` row is upserted via the
   email-draft submit handler (REG-03 T247).

For consultations that do not produce a marketing email,
**`marketing` remains in `PENDING` forever** — by design, since there
is nothing to acknowledge. Callers that need to drive `all_passed=true`
without an email draft can either (a) create+submit a draft with
`marketing_classified=true`, or (b) treat marketing as
out-of-scope for the four-gate aggregate (the current consultation
"completed" check at `lib/compliance.consultationCanComplete` only
gates on `suitability_checked` + `explanation_checked` already).

### 5. Acknowledge (after pre-check)

```http
POST /consultations/{consultation_id}/four-gate/{gate_name}/acknowledge
Authorization: Bearer {PB|WM access token}

→ 200
{
  "gate_name": "suitability" | "explanation" | "unfair_solicitation" | "marketing",
  "gate_status": "ACKNOWLEDGED",
  "gate_acknowledged_at": "<ISO-8601>"
}

→ 404 { "detail": "gate not found — run check first" }
   when no pre-check row exists for this gate_name
```

- Audit code: `four_gate_acknowledged`
- Resource: `consultation_gate` (the gate row id)
- Required actor role: PB or WM (per `_require_consultation_staff`).

## Read Aggregate

```http
GET /consultations/{consultation_id}/four-gate
Authorization: Bearer (any consultation-scoped role)

→ 200
{
  "consultation_id": "{uuid}",
  "all_passed": false,
  "gates": [
    {"gate_name": "suitability",         "gate_status": "PENDING|PASSED|BLOCKED|ACKNOWLEDGED", "gate_acknowledged_at": null, "gate_evidence_json": {}},
    {"gate_name": "explanation",         "gate_status": "...", ...},
    {"gate_name": "unfair_solicitation", "gate_status": "...", ...},
    {"gate_name": "marketing",           "gate_status": "...", ...}
  ]
}
```

`all_passed=true` ⇔ every gate ∈ `{PASSED, ACKNOWLEDGED}`.

## HP1 Workflow Sequence (synthetic)

For service-viability audit HP1 to emit `four_gate_acknowledged` ×4 +
each pre-check audit code, the calling order is:

```
POST /consultations                              → create
POST /consultations/{id}/suitability             → suitability row PASSED
POST /consultations/{id}/explanation-confirm     → explanation row PASSED
POST /consultations/{id}/unfair-solicitation-check → unfair_solicitation row PASSED
POST /email-drafts (marketing_classified=true)   → draft
POST /email-drafts/{id}/submit                   → marketing row PASSED (via run_marketing_gate)
POST /consultations/{id}/four-gate/suitability/acknowledge          → 200
POST /consultations/{id}/four-gate/explanation/acknowledge          → 200
POST /consultations/{id}/four-gate/unfair_solicitation/acknowledge  → 200
POST /consultations/{id}/four-gate/marketing/acknowledge            → 200
```

Audit emit (12 rows, 8 distinct codes):
1. `consultation_created`
2. `suitability_confirmed`
3. `explanation_confirmed`
4. (unfair_solicitation_blocked omitted on PASS; no audit code on PASS)
5. `email_drafted`
6. `marketing_review_passed` or `marketing_review_blocked`
7. `email_draft_submitted`
8. `four_gate_acknowledged` ×4

## Frontend Orchestration

`apps/web/src/components/ConsultationFourGatePane.tsx`:

- The acknowledge button is gated on `gate.gate_status === "PASSED"
  && !gate.gate_acknowledged_at`. Users cannot click ack when the gate
  is PENDING — this defends against the 404 path in normal UX.
- The pre-check entry points are PB/WM only and require user-provided
  payload (suitability assessment data, explanation checklist
  selections, unfair-solicitation message text, marketing email
  content). They are surfaced by the surrounding panes
  (`ConsultationWorkspacePane`, marketing flow on `EmailDraftsPage`)
  rather than by a single "run pre-check" button — by design, because
  each pre-check captures distinct evidence.
- For PENDING gates, the pane renders a help line directing the user
  to the appropriate pre-check action ("적합성 검토는 워크스페이스에서
  완료해주세요" etc.) so the pending state is actionable instead of
  silent. See ConsultationFourGatePane changes accompanying this doc.

## Roles

| endpoint                                          | roles allowed         |
|---------------------------------------------------|-----------------------|
| `POST /consultations/{id}/suitability`            | PB, WM                |
| `POST /consultations/{id}/explanation-confirm`    | PB, WM                |
| `POST /consultations/{id}/unfair-solicitation-check` | PB, WM             |
| `POST /email-drafts/{id}/submit` (drives marketing) | PB, WM              |
| `POST /consultations/{id}/four-gate/{name}/acknowledge` | PB, WM           |
| `GET /consultations/{id}/four-gate`               | any consultation-scoped role |

## References

- Source: `apps/api/harness/api/routers/consultation_gates.py`
- Aggregator: `apps/api/harness/services/four_gate.py`
- Audit emit pattern: `apps/api/harness/repositories/audit.py`
- Audit predecessor finding: `.omc/handoffs/svc-via-audit-v1__step2-axis2-workflow-e2e.md` (F6)
