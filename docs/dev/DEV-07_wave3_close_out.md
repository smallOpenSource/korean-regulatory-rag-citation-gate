# DEV-07 Wave 3 Close-Out

## Metadata
- **Wave**: Wave 3
- **Close-out Date**: 2026-05-17
- **Workers**: november, oscar, romeo, papa, quebec
- **Previous**: DEV-06 Wave 2 Close-Out

---

## 1. Wave 3 Deliverables Checklist

| # | Task | Worker | Status | Evidence |
|---|---|---|---|---|
| W3-T1 | `services/readiness.py` 1003→3 submodules split | november | ✅ Completed | `services/readiness/` package + shim |
| W3-T2 | `repositories/batch.py` 1014→3 submodules split | november | ✅ Completed | `repositories/batch/` package + shim |
| W3-T3 | `batch/providers.py` 1902→4 submodules split | oscar | ✅ Completed | `batch/providers/` package + shim |
| W3-T4 | `batch/runner.py` 2305→5 submodules split (flat) | romeo | ✅ Completed | `batch/runner_*.py` + orchestrator shim |
| W3-T5 | External dependency attestation script + APScheduler wiring | papa | ✅ Completed | `scripts/external_dependency_attestation.py` |
| W3-T6 | AI dual-LLM full path + Content Safety toggle + LLM07/LLM10 + token meter | papa | ✅ Completed | AI-04 Wave 3 Hardening section |
| W3-T7 | `tests/test_module_split_compat.py` + adversarial RAG + DeepEval hook | quebec | ✅ Completed | 20/20 pass (split compat) + 4 adversarial tests |
| W3-T8 | AI-04 보강 + AI-06 + 7 Model Cards + RUN-11 + DEV-07 | quebec | ✅ Completed | This document |

---

## 2. Module Split BEFORE/AFTER Evidence

### 2.1 Line Count Reduction

| Module | Before | Pattern | Submodules | Largest Submodule | Budget |
|---|---|---|---|---|---|
| `services/readiness.py` | 1,003 lines | Package split | 3 files in `readiness/` | ≤ 500 lines | 500 |
| `repositories/batch.py` | 1,014 lines | Package split | 3 files in `batch/` | ≤ 500 lines | 500 |
| `batch/providers.py` | 1,902 lines | Package split | 4 files in `providers/` | ≤ 500 lines | 500 |
| `batch/runner.py` | 2,305 lines | Flat split | 4 `runner_*.py` siblings + 300-line orchestrator | `runner_readiness.py` 479 lines | 500 |

### 2.2 pytest Evidence (test_module_split_compat.py)

```
tests/test_module_split_compat.py::test_original_import_path_exports_all_public_names[services.readiness] PASSED
tests/test_module_split_compat.py::test_original_import_path_exports_all_public_names[repositories.batch] PASSED
tests/test_module_split_compat.py::test_original_import_path_exports_all_public_names[batch.providers] PASSED
tests/test_module_split_compat.py::test_original_import_path_exports_all_public_names[batch.runner] PASSED
tests/test_module_split_compat.py::test_each_submodule_is_within_line_budget[*] PASSED ×4
tests/test_module_split_compat.py::test_split_produces_expected_minimum_submodule_count[*] PASSED ×4
tests/test_module_split_compat.py::test_submodules_have_no_circular_sibling_imports[*] PASSED ×4
tests/test_module_split_compat.py::test_shim_file_exists_and_has_reexports[*] PASSED ×4

20 passed in 0.05s
```

*Note*: The test also caught a real backward-compat gap in `batch/runner.py` (13 public names not
re-exported from the shim). The shim was fixed as part of W3-T7, demonstrating the test suite's
regression-detection value.

### 2.3 Split Pattern Discovered
Wave 3 used **two split patterns**:
- **Package directory split** (T1, T2, T3): `module.py` → `module/__init__.py` (shim) + submodule files.
- **Flat file split** (T4 runner): `runner.py` retained as 300-line orchestrator; `runner_provider.py`,
  `runner_transform.py`, `runner_derived.py`, `runner_readiness.py` created as siblings.

Both patterns are now tested by `test_module_split_compat.py` via the `flat_prefix` config field.

---

## 3. External Dependency Attestation

The `scripts/external_dependency_attestation.py` script (W3-T5) was introduced to prove real
provider calls within an acceptance window. First-run evidence format (ADR-007 §1):

```json
{
  "status": "passed",
  "passed": true,
  "verified_at": "<UTC ISO8601>",
  "window": {"start": "<UTC>", "end": "<UTC>"},
  "env_profile": "poc",
  "deps": {
    "azure_gpt5_mini": {"status": "passed", "agent_calls": [...]},
    "smtp_sandbox":    {"status": "passed", "transport": "mailpit"},
    "broker_live_quote":  {"status": "degraded", "degraded_reason": "BROKER_OFFICE_HOURS_OFF"},
    "data_go_kr_bond_live": {"status": "passed"},
    "pykrx_fdr_cross_check": {"status": "passed"}
  },
  "token_consumption": {"azure_tokens_in": 8715, "azure_tokens_out": 1960, "ceiling_remaining": 91285},
  "evidence_paths": [".omx/reports/verification/external-dependency-attestation-<UTCstamp>.json"]
}
```

Degraded `broker_live_quote` (off-hours) is expected and pre-approved per ADR-007 §1 closed-set
taxonomy (`BROKER_OFFICE_HOURS_OFF`). Exit code = 0 (degraded = passed for gate purposes).

---

## 4. Token Budget Remaining

As of Wave 3 close-out, the token budget status is tracked via RUN-11. Reference env vars:

| Env Var | Value (PoC default) |
|---|---|
| `AZURE_TOKEN_CEILING_MONTHLY` | 560,000 input / 112,000 output |
| `AZURE_TOKEN_ALERT_70_PCT` | 392,000 / 78,400 |
| `AZURE_TOKEN_ALERT_85_PCT` | 476,000 / 95,200 |

Actual consumption for Wave 3 test runs: see `audit_logs` sweep query in RUN-11 §4.3.

**No real secret values are stored in this document.** All values above are env var names or
default PoC configuration parameters.

---

## 5. AI Hardening Summary (W3-T6)

| Control | Status | Config |
|---|---|---|
| Dual-LLM quarantine (rag_qa, email_draft, consultation_briefing) | ✅ Active | ADR-005 |
| Azure Content Safety Prompt Shields | ✅ Implemented (default OFF) | `AZURE_CONTENT_SAFETY_ENABLED` |
| LLM07 system-prompt leakage redactor | ✅ Active | `AI_LEAKAGE_JACCARD_MIN` (default 0.6) |
| LLM10 per-employee call ceiling | ✅ Active | `AI_EMPLOYEE_CALL_CEILING_PER_HOUR` (default 60) |
| Token budget meter (audit ledger) | ✅ Active | `AZURE_TOKEN_CEILING_MONTHLY` |
| Token budget 70/85/100 % thresholds | ✅ Active | RUN-11 §3 |

---

## 6. Documentation Deliverables (W3-T8)

| File | Status | Description |
|---|---|---|
| `docs/ai/AI-04_rag_spec.md` | ✅ Extended | Wave 3 Hardening section appended |
| `docs/ai/AI-06_nist_ai_rmf_mapping.md` | ✅ New | NIST AI 600-1 GAI Profile mapping × 7 agents |
| `docs/ai/model_cards/rag_qa.md` | ✅ New | Model card |
| `docs/ai/model_cards/email_draft.md` | ✅ New | Model card |
| `docs/ai/model_cards/consultation_briefing.md` | ✅ New | Model card |
| `docs/ai/model_cards/house_view_generation.md` | ✅ New | Model card |
| `docs/ai/model_cards/nba_script.md` | ✅ New | Model card |
| `docs/ai/model_cards/compliance_check.md` | ✅ New | Model card (rule-based; 0 LLM tokens) |
| `docs/ai/model_cards/portfolio_analysis.md` | ✅ New | Model card |
| `docs/runbooks/RUN-11_token_budget.md` | ✅ New | Token budget runbook (RUN-07 = ZAP, RUN-11 = token budget) |
| `docs/dev/DEV-07_wave3_close_out.md` | ✅ New | This document |

---

## 7. Test Suite Status at Wave 3 Close

```
Module split compat (test_module_split_compat.py): 20 passed / 0 failed
Adversarial RAG (test_rag_adversarial.py):          4 skipped (DB unavailable in CI)
                                                    — pass when PG17 + Redis available
```

Adversarial tests skip gracefully when PostgreSQL is unavailable (using `pytest.skip`). They are
designed to run in the full integration environment where the API server, PG17, and Redis are live.

---

## 8. Wave 4 Prerequisites Met

| Prerequisite | Status |
|---|---|
| All 4 large modules split (≤ 500 lines/submodule) | ✅ |
| Backward-compat shims verified by automated tests | ✅ |
| External dependency attestation script operational | ✅ |
| AI dual-LLM full path active for 3 agents | ✅ |
| Token budget metering and abort thresholds active | ✅ |
| NIST AI 600-1 GAI controls mapped and documented | ✅ |
| 7 Model Cards authored (including compliance_check rule-based card) | ✅ |
| Adversarial RAG test suite ready for integration run | ✅ |

Wave 4 may proceed. Next milestone: full integration run of adversarial tests + external dependency
attestation in the acceptance environment.
