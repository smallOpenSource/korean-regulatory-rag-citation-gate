# ARCH-01 Stage 0.5 Architecture Contract Inventory

## Purpose
Stage 0.5 freezes architecture-facing contracts before feature implementation widens. This
inventory is intentionally documentation- and validator-first: it does not add backend routes,
provider clients, dependencies, or database migrations. It records the contract gates that later
implementation lanes must satisfy before moving a roadmap feature into `docs/api/API-01_contracts.yaml`.

## Current Status Matrix
| Contract area | Current implementation status | Contract artifact | Validation scaffold |
|---|---|---|---|
| WebSocket delivery | `backlog/not-current-contract`; frontend helper exists but no FastAPI `/ws` route is in API-01 | `docs/architecture/ADR-001_websocket_delivery_contract.md`, `docs/api/API-02_websocket.md` | `scripts/validate_architecture_contracts.py` |
| Email draft/send | current backend HTTP contract; `/email-drafts` and `/email-drafts/{draft_id}/send` use PB/WM row scope, APPROVED-only send, SMTP fail-closed provider gate, and audit-on-real-send | `docs/architecture/ADR-002_email_authority_and_schema_contract.md`, `docs/integration/INT-03_email.md` | `scripts/validate_architecture_contracts.py`, API boundary harness |
| Dependency changes | frozen without an ADR and manifest allowlist update | `docs/architecture/ADR-003_dependency_change_gate.md` | `scripts/validate_architecture_contracts.py` |
| Large modules | existing large files are contained; new growth requires split plan before feature work | `docs/dev/DEV-02_large_module_containment.md` | `scripts/validate_architecture_contracts.py` |
| Operations status | status/runbook path is local scripts + `/health`, `/batch/status`, `/data/readiness`; no push alert is current contract | `docs/runbooks/OPS-04_operations_status.md` | `scripts/status.sh --deep --no-fail`, `scripts/validate_architecture_contracts.py` |

## Promotion Rules
1. A roadmap route or event becomes current contract only after code, API docs, auth/row-scope tests,
   observability notes, and runbook operations evidence land together.
2. API-01 remains the implemented HTTP contract. API-02 and other future-only artifacts must label
   non-implemented surfaces as `backlog/not-current-contract`; INT-03 now documents the implemented
   email backend contract plus future recipient/approval metadata extensions.
3. Raw SQL remains the only database access pattern. New SQL or migrations must keep leading
   `/* sql_id: ... */` comments and must not introduce an ORM or migration framework.
4. No mocks, local simulators, or fabricated provider rows may be used to turn a contract green.
5. Docs sync is required when any listed contract area changes; run
   `/opt/conda/envs/wm_env/bin/python scripts/validate_architecture_contracts.py` before
   handing off for final verification.
