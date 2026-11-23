# Task 8 — Post-merge frontend role/session verification

Scope: frontend role navigation, Korean UX, critical protected-screen session behavior, and reload-safe auth checks after Task 4 integration.

## Commands run from `apps/web`

| Check | Result | Evidence |
|---|---|---|
| `npm run typecheck` | PASS | `tsc --noEmit` exited 0. |
| `npm test` | PASS | Vitest reported 8 passed test files and 23 passed tests. |
| `npm run lint` | PASS | `eslint .` exited 0. |
| `npm run build` | PASS | `tsc --noEmit && vite build` exited 0; Vite transformed 109 modules. |
| `npm run e2e` | PASS with credential skips | Playwright reported 1 passed anonymous protected-route/login notice smoke and 10 skipped credential-gated tests. |

## Verified behavior

- Korean sidebar navigation is still role-filtered through the route access table used by `ProtectedRoute`.
- PB users see PB/WM workflow links while admin-only screens are hidden.
- ADMIN users see admin/audit links while PB/WM-only action links are hidden.
- AUDIT_VIEWER users see read-only dashboard/house-view/audit navigation only.
- Protected reloads show Korean session-restore guidance before redirecting.
- Restored admin memory sessions resume the protected batch screen without browser token storage.

## Skips / constraints

- Credential-backed Playwright role matrix/live employee flows were skipped because `E2E_SYNTHETIC_PASSWORD` and live employee credentials were not configured in this worker pane.
- Vite emitted the existing dynamic/static `src/lib/api.ts` chunking warning during build/e2e preview; it did not fail verification.
