# Task 9 — UI/API contract drift review after merged changes

Scope: read-mostly frontend/API drift review for Korean role navigation, protected route permissions, UI copy regressions, and reload-safe session behavior after the latest team merges.

## Contract comparison

| Area | Source checked | Frontend checked | Result |
|---|---|---|---|
| Protected routes | `docs/ui/UI-01_screen_list.md`, `docs/security/SEC-01_auth_spec.md`, `docs/api/API-01_contracts.yaml` | `src/App.tsx`, `src/lib/access.ts`, `e2e/role-matrix.spec.ts` | PASS — screen paths and role sets remain aligned for dashboard, customers/customer360, consultation, NBA, house views, activation, RAG, batch, and audit. |
| Sidebar role navigation | `src/lib/access.ts` as route permission source | `src/components/Layout.tsx`, `src/tests/layout-navigation.test.tsx` | PASS — navigation filters links through `canAccessRoute`; PB, ADMIN, and AUDIT_VIEWER expectations are regression-tested. |
| Reload/session UX | `docs/security/SEC-01_auth_spec.md` refresh-cookie boundary | `src/store/auth.ts`, `src/lib/api.ts`, `src/components/ProtectedRoute.tsx`, `src/tests/auth-session*.test*` | PASS — refresh uses `credentials: "include"`, protected screens wait on restore state, and tests assert no `localStorage`/`sessionStorage` token persistence. |
| Korean UI copy | Korean-first copy tests and banned placeholder patterns | `src/tests/korean-copy-regression.test.ts`, `src/tests/ui-copy-smoke.test.tsx`, rendered login/protected copy tests | PASS — current test suite passed, including Korean copy and raw status/placeholder guards. |
| E2E critical smoke | Playwright critical route/login notice coverage | `e2e/harness-critical.spec.ts`, `e2e/role-matrix.spec.ts` | PASS with credential skips — anonymous protected route/login notice smoke passed; credential-backed role/live flows self-skipped due missing env. |

## Verification commands run from `apps/web`

| Check | Result | Evidence |
|---|---|---|
| `npm run typecheck` | PASS | `tsc --noEmit` exited 0 after restoring this worker's local `node_modules`. |
| `npm test` | PASS | Vitest reported 8 passed test files and 23 passed tests. |
| `npm run lint` | PASS | `eslint .` exited 0. |
| `npm run build` | PASS | `tsc --noEmit && vite build` exited 0; Vite transformed 109 modules. |
| `npm run e2e` | PASS with credential skips | Playwright reported 1 passed anonymous protected-route/login notice smoke and 10 skipped credential-gated tests. |

## Environment note

An initial `npm run typecheck` attempt failed without TypeScript diagnostics because this worker pane's ignored `apps/web/node_modules` symlink resolved through `<repo-root>/apps/web/node_modules` and `worker-1/apps/web/node_modules`, producing a symlink loop (`tsc` exit 216 / `Too many levels of symbolic links`). The symlink was removed only in this worker worktree and `npm ci` restored a local ignored dependency install before verification was rerun successfully.

## Drift verdict

No immediate frontend/API contract drift requiring product-code changes was found. The only committed change for this task is this verification artifact for final validator handoff.

## Known skips / constraints

- Credential-backed Playwright role matrix and live employee flows were skipped because `E2E_SYNTHETIC_PASSWORD`, `E2E_EMPLOYEE_EMAIL`, and `E2E_EMPLOYEE_PASSWORD` were not configured in this worker pane.
- Vite emitted the existing dynamic/static `src/lib/api.ts` chunking warning during build/e2e preview; it did not fail verification.
