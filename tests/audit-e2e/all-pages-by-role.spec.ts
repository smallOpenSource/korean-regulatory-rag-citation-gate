import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

/**
 * WMAH Audit — Stage 2 Lane 1
 *
 * Visits every page (23 page files in apps/web/src/pages/) for every audited
 * role (PB, WM, ADMIN, AUDIT_VIEWER) and captures:
 *   - screenshot (full page PNG)
 *   - console messages (text log)
 *   - HAR network trace
 *   - landing URL (used to determine 200 vs 403 outcome)
 *
 * All artifacts are attached via testInfo.attach and also written under
 * testInfo.outputDir which Playwright config maps to audit-out/behavior/<test>.
 *
 * Role access matrix is the authoritative table mirrored from
 *   apps/web/src/lib/access.ts (ACCESS_RULES)
 * — do not mutate this map without updating access.ts and the role allowlists
 * emitted by the audit (audit-out/stage-2/a11y/target-pages.json,
 * audit-out/stage-2/playwright/page-route-map.md).
 */

type RoleCode = "PB" | "WM" | "ADMIN" | "AUDIT_VIEWER";
type RouteKey =
  | "public"
  | "dashboard"
  | "customers"
  | "customer360"
  | "consultation"
  | "nba"
  | "aftercare"
  | "emailDrafts"
  | "houseViews"
  | "houseViewActivation"
  | "rag"
  | "batch"
  | "audit"
  | "auditViewer"
  | "rightsNotice"
  | "disputeCase"
  | "aiModelCards"
  | "aiPolicy"
  | "koreanAIAct"
  | "aiAdminDashboard"
  | "quarantine"
  | "autopilotDemo";

const ACCESS_RULES: Record<Exclude<RouteKey, "public">, RoleCode[]> = {
  dashboard: ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
  customers: ["PB", "WM", "ADMIN"],
  customer360: ["PB", "WM", "ADMIN"],
  consultation: ["PB", "WM"],
  nba: ["PB", "WM"],
  aftercare: ["PB", "WM", "ADMIN"],
  emailDrafts: ["PB", "WM"],
  houseViews: ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
  houseViewActivation: ["ADMIN"],
  rag: ["PB", "WM", "ADMIN"],
  batch: ["ADMIN"],
  audit: ["ADMIN", "AUDIT_VIEWER"],
  auditViewer: ["ADMIN", "AUDIT_VIEWER"],
  rightsNotice: ["PB", "WM", "ADMIN"],
  disputeCase: ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
  aiModelCards: ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
  aiPolicy: ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
  koreanAIAct: ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
  aiAdminDashboard: ["ADMIN"],
  quarantine: ["ADMIN"],
  autopilotDemo: ["PB", "WM", "ADMIN"],
};

interface PageEntry {
  pageFile: string;
  routeKey: RouteKey;
  urlPath: string;
}

/**
 * 23 page files in apps/web/src/pages/, mapped to their representative route.
 * LoginPage and ForbiddenPage are public (no role gate); the remaining 21
 * map to ACCESS_RULES via their routeKey. HouseViewDetailPage is the same
 * component for both /house-views/:id and /house-views/:id/activate — the
 * `/activate` route is covered by the houseViewActivation row to assert
 * ADMIN-only access (BRANCH_MANAGER is excluded from this audit lane).
 */
const PAGES: PageEntry[] = [
  { pageFile: "AftercarePage.tsx", routeKey: "aftercare", urlPath: "/aftercare" },
  { pageFile: "AIAdminDashboardPage.tsx", routeKey: "aiAdminDashboard", urlPath: "/ai-admin-dashboard" },
  { pageFile: "AIModelCardsPage.tsx", routeKey: "aiModelCards", urlPath: "/ai-model-cards" },
  { pageFile: "AIPolicyPage.tsx", routeKey: "aiPolicy", urlPath: "/ai-policy" },
  { pageFile: "AuditPage.tsx", routeKey: "audit", urlPath: "/audit" },
  { pageFile: "AuditViewerPage.tsx", routeKey: "auditViewer", urlPath: "/audit-viewer" },
  { pageFile: "AutopilotDemoPage.tsx", routeKey: "autopilotDemo", urlPath: "/autopilot-demo" },
  { pageFile: "BatchPage.tsx", routeKey: "batch", urlPath: "/batch" },
  { pageFile: "ConsultationPage.tsx", routeKey: "consultation", urlPath: "/consultations/CONS-AUDIT-0001" },
  { pageFile: "Customer360Page.tsx", routeKey: "customer360", urlPath: "/customers/CUST-AUDIT-0001" },
  { pageFile: "CustomersPage.tsx", routeKey: "customers", urlPath: "/customers" },
  { pageFile: "DashboardPage.tsx", routeKey: "dashboard", urlPath: "/dashboard" },
  { pageFile: "DisputeCasePage.tsx", routeKey: "disputeCase", urlPath: "/dispute-cases" },
  { pageFile: "EmailDraftsPage.tsx", routeKey: "emailDrafts", urlPath: "/email-drafts" },
  { pageFile: "ForbiddenPage.tsx", routeKey: "public", urlPath: "/403" },
  { pageFile: "HouseViewDetailPage.tsx", routeKey: "houseViewActivation", urlPath: "/house-views/HV-AUDIT-0001/activate" },
  { pageFile: "HouseViewsPage.tsx", routeKey: "houseViews", urlPath: "/house-views" },
  { pageFile: "KoreanAIBasicActPage.tsx", routeKey: "koreanAIAct", urlPath: "/korean-ai-act" },
  { pageFile: "LoginPage.tsx", routeKey: "public", urlPath: "/login" },
  { pageFile: "NbaPage.tsx", routeKey: "nba", urlPath: "/nba" },
  { pageFile: "QuarantineDashboard.tsx", routeKey: "quarantine", urlPath: "/quarantine" },
  { pageFile: "RagPage.tsx", routeKey: "rag", urlPath: "/rag" },
  { pageFile: "RightsNoticePage.tsx", routeKey: "rightsNotice", urlPath: "/rights-notice" },
];

const ROLES: RoleCode[] = ["PB", "WM", "ADMIN", "AUDIT_VIEWER"];

const STORAGE_STATE_DIR = path.resolve(__dirname, "../../audit-out/stage-0");

function storageStatePath(role: RoleCode): string {
  return path.join(STORAGE_STATE_DIR, `storageState-${role}.json`);
}

// Wave-Audit-Defect-Fix F2: per-test fresh login fixture. Stale storageState
// shared across all tests in a role describe causes JTI rotation collisions
// (one early test's /auth/refresh blocklists the old JTI; later tests using
// the same storageState then 401). Driving each test through a fresh UI
// login (or programmatic login when env flag set) eliminates that collision.
//
// The auth bootstrap pattern is copied from audit-out/stage-0/create-storage-state.mjs
// so the spec stays consistent with the canonical create-storage-state flow.
const ROLE_EMAILS: Record<RoleCode, string> = {
  PB: "synthetic.pb1@example.invalid",
  WM: "synthetic.wm1@example.invalid",
  ADMIN: "synthetic.admin@example.invalid",
  AUDIT_VIEWER: "synthetic.audit@example.invalid",
};
// A.19 fix: canonical synthetic password lives in audit-out/stage-0/create-storage-state.mjs.
// Earlier Z3 runs set E2E_SYNTHETIC_PASSWORD (different env var name), so this spec
// silently fell back to the dev-only DemoPass!! and every login returned 401, which
// then surfaced as the waitForURL 20s timeout misdiagnosed as a JTI rotation race.
const E2E_PASSWORD =
  process.env.WMAH_E2E_PASSWORD ??
  process.env.E2E_SYNTHETIC_PASSWORD ??
  "HarnessSynthetic!2026";

async function freshLogin(page: Page, role: RoleCode): Promise<void> {
  const email = ROLE_EMAILS[role];
  // Per-test BrowserContext hygiene (2026-05-23 OQ-5 follow-up
  // diagnosis): the prior test's session leaves a stale refresh
  // cookie + Zustand store snapshot in the shared BrowserContext.
  // Each test's first action loads /login which may trigger an
  // automatic restoreSession() refresh on the prior token, racing
  // the new login flow. Clearing cookies + storage before the
  // first attempt forces a deterministic blank slate.
  await page.context().clearCookies().catch(() => {});
  await page.goto("about:blank").catch(() => {});
  await page.evaluate(() => {
    try { localStorage.clear(); } catch {}
    try { sessionStorage.clear(); } catch {}
  }).catch(() => {});

  // Two-attempt loop with 30s timeout each: the WMAH login flow rotates
  // the JTI server-side and the React client re-renders before the
  // access_token has committed to the store. waitForURL alone can race
  // even after networkidle. The retry pattern keeps the 3 hard failures
  // surfaced in 2026-05-23 cycle (PB::EmailDrafts, WM::Consultation,
  // ADMIN::Forbidden — all login-stage races, NOT route-guard defects)
  // within the same lane without leaking into Playwright's outer retry.
  let lastError: unknown = undefined;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      await page.goto("/login", { waitUntil: "networkidle", timeout: 20_000 });
      await page.fill('input[type="email"]', email);
      await page.fill('input[type="password"]', E2E_PASSWORD);
      await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 }),
        page.click('button[type="submit"]'),
      ]);
      // Explicit access_token commit wait — Zustand useAuthStore holds
      // the token in-memory (apps/web/src/store/auth.ts) and a
      // post-login navigation can race the setSession() commit. The
      // store is exposed in DEV builds as `window.__wmahAuth` so the
      // spec can poll the live value rather than guessing with
      // networkidle. This eliminates the JTI race documented in
      // [[bfs-auth-race-window]].
      await page.waitForFunction(
        () => {
          const w = window as unknown as { __wmahAuth?: { getAccessToken: () => string | null } };
          return Boolean(w.__wmahAuth?.getAccessToken());
        },
        undefined,
        { timeout: 10_000 },
      );
      return;
    } catch (error) {
      lastError = error;
      // Reset to a clean page before the next attempt so any half-set
      // localStorage / cookie state doesn't leak into the retry.
      await page.context().clearCookies().catch(() => {});
      await page.goto("about:blank").catch(() => {});
      await page.waitForTimeout(500);
    }
  }
  throw lastError;
}

function expectedAllowed(entry: PageEntry, role: RoleCode): boolean {
  if (entry.routeKey === "public") {
    return true;
  }
  const allow = ACCESS_RULES[entry.routeKey];
  return allow.includes(role);
}

function slugify(input: string): string {
  return input.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_|_$/g, "");
}

async function collectConsole(page: Page): Promise<string[]> {
  const messages: string[] = [];
  page.on("console", (msg) => {
    messages.push(`[${msg.type()}] ${msg.text()}`);
  });
  page.on("pageerror", (err) => {
    messages.push(`[pageerror] ${err.message}`);
  });
  return messages;
}

test.describe("WMAH audit — all pages by role", () => {
  for (const role of ROLES) {
    const statePath = storageStatePath(role);
    const stateExists = fs.existsSync(statePath);

    test.describe(`role=${role}`, () => {
      // Wave-Audit-Defect-Fix F2: storageState is the FALLBACK fixture only;
      // per-test fresh login (below in beforeEach) is the primary auth path
      // and bypasses the JTI rotation collision. Setting WMAH_E2E_USE_STORAGE_STATE=1
      // restores the legacy shared-storageState behaviour for diagnostic comparison.
      const useStorageState = process.env.WMAH_E2E_USE_STORAGE_STATE === "1";
      test.use(useStorageState && stateExists ? { storageState: statePath } : {});

      test.beforeEach(async ({ page }) => {
        if (useStorageState && stateExists) {
          return; // legacy path; skip fresh login
        }
        await freshLogin(page, role);
      });

      for (const entry of PAGES) {
        const allowed = expectedAllowed(entry, role);
        const expectedOutcome = allowed ? "200" : "403";
        const title = `${role} :: ${entry.pageFile} :: expect=${expectedOutcome}`;

        test(title, async ({ page }, testInfo) => {
          test.skip(!stateExists, `storageState missing: ${statePath}`);

          const consoleMessages = await collectConsole(page);
          const harPath = path.join(
            testInfo.outputDir,
            `${slugify(role)}__${slugify(entry.pageFile)}.har`,
          );
          await page.routeFromHAR(harPath, { update: true }).catch(() => {
            /* HAR recording best-effort */
          });

          // Auth bootstrap: first navigate to root to trigger restoreSession (cookie→/auth/refresh→access_token).
          // Then wait for either user state restored OR explicit /login redirect.
          await page.goto("/", { waitUntil: "domcontentloaded" });
          await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
          // Post-bootstrap auth wait: poll __wmahAuth.getAccessToken() until
          // the in-memory Zustand store re-hydrates from the refresh cookie.
          // Stronger than __wmahPageReady (which fires regardless of restore
          // success); R6 measurement (87/2/3) beat R7 with __wmahPageReady
          // (84/5/3) because false-restore signals propagated to spec.
          await page.waitForFunction(
            () => {
              const w = window as unknown as { __wmahAuth?: { getAccessToken: () => string | null } };
              return Boolean(w.__wmahAuth?.getAccessToken());
            },
            undefined,
            { timeout: 10_000 },
          ).catch(() => {});
          await page.waitForTimeout(700);

          let navResult = await page.goto(entry.urlPath, { waitUntil: "domcontentloaded" });
          await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {
            /* networkidle may not settle for streaming pages; continue anyway */
          });
          // Same post-goto auth wait — after the target navigation reloads
          // the SPA shell, restoreSession fires again and ProtectedRoute
          // can race the async restore. Poll for token re-presence before
          // asserting on the landed URL.
          await page.waitForFunction(
            () => {
              const w = window as unknown as { __wmahAuth?: { getAccessToken: () => string | null } };
              return Boolean(w.__wmahAuth?.getAccessToken());
            },
            undefined,
            { timeout: 10_000 },
          ).catch(() => {});

          // Login-redirect retry pattern: if landed on /login but expected
          // to access, give up to 3 attempts × (700ms wait + reload) per
          // [[bfs-auth-race-window]]. Empirical (2026-05-23 observability
          // cycle Item 4): the prior single-retry pattern still allowed a
          // ~1/9 flakiness on AUDIT_VIEWER + EmailDraftsPage where the
          // zustand restoreSession needed an additional cycle to settle
          // before the React route gate could resolve.
          for (let retry = 0; retry < 3; retry++) {
            if (entry.routeKey === "public" || !/\/login(\?|$|#)/.test(page.url())) {
              break;
            }
            await page.waitForTimeout(700);
            navResult = await page.goto(entry.urlPath, { waitUntil: "domcontentloaded" });
            await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
          }

          const landedUrl = page.url();
          const httpStatus = navResult?.status() ?? 0;
          const landedOn403 = /\/403(\?|$|#)/.test(landedUrl);
          const landedOnLogin = /\/login(\?|$|#)/.test(landedUrl);

          // Outcome classification:
          //   allowed=true  → must NOT redirect to /403
          //   allowed=false → must redirect to /403 (ProtectedRoute Navigate)
          // Public pages (login/403) are always allowed — and importantly,
          // when the test target IS the ForbiddenPage itself (routeKey
          // "public", urlPath "/403"), landing on /403 is the success
          // condition, not a forbidden-redirect signal. Excluding
          // public-route entries from the landedOn403 branch fixes the
          // false-positive "403" classification that previously flipped
          // ForbiddenPage to FAIL across all four roles.
          const observedOutcome = entry.routeKey !== "public" && landedOn403
            ? "403"
            : landedOnLogin && entry.routeKey !== "public"
              ? "login"
              : "200";

          const screenshotPath = path.join(
            testInfo.outputDir,
            `${slugify(role)}__${slugify(entry.pageFile)}.png`,
          );
          await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {
            /* screenshot may fail on auth interstitial; continue */
          });

          const consoleLogPath = path.join(
            testInfo.outputDir,
            `${slugify(role)}__${slugify(entry.pageFile)}.console.log`,
          );
          fs.writeFileSync(consoleLogPath, consoleMessages.join("\n"), "utf-8");

          const summary = {
            role,
            pageFile: entry.pageFile,
            routeKey: entry.routeKey,
            urlPath: entry.urlPath,
            expectedOutcome,
            observedOutcome,
            httpStatus,
            landedUrl,
            consoleErrorCount: consoleMessages.filter((m) => m.startsWith("[error]") || m.startsWith("[pageerror]")).length,
          };
          const summaryPath = path.join(
            testInfo.outputDir,
            `${slugify(role)}__${slugify(entry.pageFile)}.summary.json`,
          );
          fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2), "utf-8");

          await testInfo.attach("screenshot", { path: screenshotPath, contentType: "image/png" }).catch(() => {});
          await testInfo
            .attach("console", { path: consoleLogPath, contentType: "text/plain" })
            .catch(() => {});
          await testInfo
            .attach("summary", { path: summaryPath, contentType: "application/json" })
            .catch(() => {});
          if (fs.existsSync(harPath)) {
            await testInfo.attach("har", { path: harPath, contentType: "application/json" }).catch(() => {});
          }

          // Assertion: observed outcome must match expected role gate.
          // We do NOT assert on console errors here (Lane 1 records them; a
          // dedicated console-error gate runs in a subsequent lane).
          expect.soft(observedOutcome, `landedUrl=${landedUrl}`).toBe(expectedOutcome);
        });
      }
    });
  }
});
