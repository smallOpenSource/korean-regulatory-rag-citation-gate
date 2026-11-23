# ADR-003 Dependency Change Gate

## Status
Accepted. Dependency additions, removals, or major upgrades require an ADR update before code lands.

## Context
The PoC has strict raw-SQL, no-mock, no-fabricated-provider-row constraints. New libraries can
accidentally add ORMs, test doubles, browser storage helpers, migration frameworks, or provider
wrappers that weaken those constraints. The dependency gate keeps manifest changes visible and
reviewable.

## Decision
Any change to `pyproject.toml` dependencies or `apps/web/package.json` dependencies/devDependencies
must update this ADR with:

1. package name and manifest section,
2. reason for use,
3. rejected lighter alternative,
4. security/secret-handling impact,
5. verification command that exercised the package.

Forbidden without a separate approved architecture decision:
- ORM/migration frameworks replacing the custom raw-SQL migrator,
- browser token persistence helpers,
- mock/test-double frameworks for checked-in API/UI contract tests,
- provider wrappers that hide source lineage or fabricate rows.

## Current Dependency Manifest Allowlist
The validator reads this table. Keep package names exact and one package per row.

| ecosystem | package | reason | status |
|---|---|---|---|
| python | asyncpg | PostgreSQL raw SQL driver | allowed |
| python | fastapi | API framework | allowed |
| python | openai | Azure AI Foundry /openai/v1/ OpenAI-compatible client for gpt-5.5 (Responses API only) | allowed |
| python | pykrx | explicitly labelled auxiliary KRX-family source | allowed |
| python | pyyaml | INJECTION_PATTERNS.yaml + Model Card markdown loader (ADR-005 dual-LLM) | allowed |
| python | redis | Redis lock/cache/status dependency | allowed |
| python | uvicorn | ASGI server | allowed |
| python | websockets | uvicorn WS dispatch transport (ADR-001 realtime delivery) | allowed |
| python | wsproto | uvicorn WS dispatch protocol layer (paired with websockets) | allowed |
| js-runtime | @tanstack/react-query | server-state cache and refetch orchestration | allowed |
| js-runtime | @tailwindcss/vite | Tailwind Vite integration | allowed |
| js-runtime | react | SPA view layer | allowed |
| js-runtime | react-dom | React DOM renderer | allowed |
| js-runtime | react-router-dom | protected route/navigation layer | allowed |
| js-runtime | recharts | charts for dashboard/readiness visualization | allowed |
| js-runtime | tailwindcss | styling system | allowed |
| js-runtime | zustand | memory-only auth/session state | allowed |
| js-dev | @eslint/js | lint rules | allowed |
| js-dev | @playwright/test | real browser E2E, not API mocking | allowed |
| js-dev | @testing-library/jest-dom | DOM assertions | allowed |
| js-dev | @testing-library/react | component rendering assertions | allowed |
| js-dev | @testing-library/user-event | user interaction helpers | allowed |
| js-dev | @types/node | TypeScript Node types | allowed |
| js-dev | @types/react | TypeScript React types | allowed |
| js-dev | @types/react-dom | TypeScript React DOM types | allowed |
| js-dev | @vitejs/plugin-react | Vite React plugin | allowed |
| js-dev | eslint | lint runner | allowed |
| js-dev | eslint-plugin-react-hooks | hook linting | allowed |
| js-dev | eslint-plugin-react-refresh | Vite/React refresh linting | allowed |
| js-dev | globals | eslint global definitions | allowed |
| js-dev | jsdom | DOM environment for component tests | allowed |
| js-dev | typescript | typechecking | allowed |
| js-dev | typescript-eslint | TypeScript lint parser/rules | allowed |
| js-dev | vite | dev/build tool | allowed |
| js-dev | vitest | frontend unit runner without checked-in mocks | allowed |
| python | reportlab | synthetic PDF generation for T208 합성 계약서 (금소법 §23) + T307 워터마크 stamping (REG-06 §8). pure-python, no system libs, BSD-licensed (Stage 7 amendment 2026-05-18). | allowed |
| python | pypdf | PDF read + page-merge for T307 watermark overlay on third-party PDFs + audit-time text-extraction verification of T208 outputs. pure-python, BSD-3-Clause (Stage 7 amendment 2026-05-18). | allowed |
| tool | mailpit | SMTP sandbox container for live email delivery green-path evidence; synthetic-only recipients (Stage 2 T18, T207, T224) | pre-approved |
| tool | gitleaks | binary pre-commit + CI secret static scan; detects hardcoded keys/tokens before merge (Stage 1 T288, Stage 7) | pre-approved |

## §3 Already-Approved Additions (pre-seeded per RALPLAN-DR Iteration 2 P-8)

These packages are pre-approved for the Waves 1–5 implementation cycle. Each entry satisfies the four-field
requirement from §Decision above. No further ADR amendment is needed before use; the implementing worker
must add the package to the relevant manifest (`pyproject.toml` for python, Docker Compose for tool) and
move the entry from §3 into the "Current Dependency Manifest Allowlist" table above (so the static gate
`validate_architecture_contracts.py` stays green). The python entries below are intentionally absent from
the allowlist table until their manifest addition lands — the validator only checks manifest↔table parity
for `python`/`js-runtime`/`js-dev` ecosystems; `tool` entries are documented here for human review only.

### mailpit

| Field | Value |
|---|---|
| Manifest | Docker Compose service `mailpit` (not pip/npm; binary/container) |
| Reason | SMTP sandbox for live email delivery evidence (T18, T207, T224). Harness sends to synthetic `@example.invalid` recipients; Mailpit captures without forwarding. Replaces previously undecided "Mailpit/MailHog" placeholder. |
| Rejected alternative | MailHog — unmaintained since 2022; no active security patches; Mailpit is the maintained successor with identical API surface. |
| Security / secret handling | No secrets stored inside container; only synthetic recipients allowed; sandbox isolated to PoC network; `MAILPIT_SMTP_AUTH_*` env vars if auth enabled. |
| Verification | `curl -s http://localhost:8025/api/v1/info \| python -m json.tool` returns `{"Version":...}` after `docker compose up mailpit -d`. |

### deepeval

| Field | Value |
|---|---|
| Manifest | `pyproject.toml` `[project.optional-dependencies] dev` or `test` group |
| Reason | pytest evaluation harness for RAG golden 10건 + 7-agent golden snapshot; computes faithfulness, answer-relevancy, contextual-precision scores without custom scoring code (T260, T266). |
| Rejected alternative | Custom assertion scripts — would require reimplementing G-Eval / faithfulness / RAG triad metrics; no standard baseline; brittle to prompt changes. |
| Security / secret handling | In CI: cassette-only mode, zero live tokens. In demo: calls Azure via existing `AZURE_OPENAI_API_KEY` env var (already in scope); no new secret surface. |
| Verification | `python -m pytest tests/ai/test_deepeval_hook.py -q` passes with cassettes present. |

### slowapi

| Field | Value |
|---|---|
| Manifest | `pyproject.toml` `[project.dependencies]` |
| Reason | ASGI-native rate limiter for FastAPI; provides `/auth/*` IP+username strict limit (5 req/min) and global per-IP limit (100 req/min) required by T280, T292. |
| Rejected alternative | Custom middleware — more code to maintain; no battle-tested ASGI integration; header-extraction edge cases (X-Forwarded-For, IPv6) require duplication of slowapi internals. |
| Security / secret handling | No secrets; reads IP from request headers only; limit state stored in Redis (existing dependency). |
| Verification | `python -m pytest tests/test_config_security.py -q -k rate_limit` passes. |

### APScheduler

| Field | Value |
|---|---|
| Manifest | `pyproject.toml` `[project.dependencies]` |
| Reason | Env-driven durable cron scheduler for batch pipeline jobs (T24); Redis-backed job locks prevent concurrent provider runs; retry/timeout/concurrency configured from `.env` without hardcoded schedules. |
| Rejected alternative | Custom cron scripts — lack durable scheduling, Redis locking, per-job retry policies, and misfire handling; would require reimplementing the same guarantees. |
| Security / secret handling | No secret access at scheduler layer; jobs receive credentials via env vars already in scope; does not execute SQL directly. |
| Verification | `python -m pytest tests/test_batch_scheduler.py -q` passes. |

### gitleaks

| Field | Value |
|---|---|
| Manifest | CI step + optional pre-commit hook (binary; not pip/npm) |
| Reason | Secret static scan in CI (T288) and Stage 7 runbook; detects hardcoded API keys, tokens, connection strings before merge; enforces `/* sql_id */`-compatible scan without blocking raw-SQL patterns. |
| Rejected alternative | Custom grep regexes — less comprehensive; no curated pattern database; high false-negative rate for base64-encoded secrets and multi-line tokens; maintenance burden. |
| Security / secret handling | Read-only scan of source tree; does not store, transmit, or log any detected secret values; exits non-zero on detection so CI blocks the merge. |
| Verification | `gitleaks detect --source . --no-git --exit-code 0` exits 0 on clean tree (run after ensuring `.env` is gitignored). |

### harness-sri (inline Vite plugin — no external package)

| Field | Value |
|---|---|
| Manifest | `apps/web/vite.config.ts` inline (no npm entry — uses Node.js built-in `crypto`) |
| Reason | Subresource Integrity for all JS/CSS bundles in `dist/index.html` (REG-05 T285). Computes SHA-384 hashes of every Rollup output chunk during `vite build` and injects `integrity="sha384-..."` + `crossorigin="anonymous"` into the generated HTML, preventing execution of tampered CDN/cache assets. |
| Rejected alternative | `vite-plugin-sri` (npm) — adds an external dependency with its own supply-chain risk for a 30-line operation; the inline implementation does the same using Node's built-in `crypto` module with no additional attestation burden. |
| Security / secret handling | No secrets accessed; operates only on local build artefacts; hash computation is deterministic and reproducible. |
| Verification | `scripts/verify_vite_sri.sh apps/web/dist/index.html` exits 0 after `npm run build`; CI gate fails if any `<script src>` or `<link stylesheet href>` tag lacks an `integrity=` attribute. |

---

## Verification
Run the static gate after manifest edits:

```bash
/opt/conda/envs/wm_env/bin/python scripts/validate_architecture_contracts.py
```

The gate fails if a manifest package is missing from the allowlist. It does not approve new
packages by itself; it only proves the docs and manifests are synchronized.
