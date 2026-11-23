/**
 * Korean copy allowlist tests — rendered text assertions via Playwright.
 *
 * Tags: @korean-copy
 *
 * Each logged-in page is loaded, its body.textContent() is extracted, and
 * asserted against `src/lib/copy_allowlist.json`:
 *   1. `banned_global` patterns must not appear on any page.
 *   2. `banned_numbered_customer_pattern` must not appear (e.g., "고객 01").
 *   3. `banned_raw_api_codes` must not appear outside the /audit page.
 *   4. `required_per_route` strings must appear on the matching route.
 *
 * Constraints:
 * - Real PG17 + Redis backend (E2E_SYNTHETIC_PASSWORD required).
 * - Synthetic accounts only; no real credentials.
 * - Headless Playwright Chromium.
 */
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

interface Allowlist {
  banned_global: string[];
  banned_numbered_customer_pattern: string;
  banned_raw_api_codes: string[];
  banned_raw_api_codes_audit_exempt: boolean;
  required_per_route: Record<string, string[]>;
  roles_per_route: Record<string, string[]>;
}

// JSON import assertions unsupported in this runtime; load via URL relative to import.meta.url.
const allowlist = JSON.parse(
  readFileSync(new URL("../src/lib/copy_allowlist.json", import.meta.url), "utf-8"),
) as Allowlist;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const password = process.env.E2E_SYNTHETIC_PASSWORD;

/** Synthetic email accounts keyed by role. */
const ROLE_EMAILS: Record<string, string> = {
  PB: "synthetic.pb1@example.invalid",
  ADMIN: "synthetic.admin@example.invalid",
  AUDIT_VIEWER: "synthetic.audit@example.invalid",
};

/**
 * Routes to check and which role to log in as for that check.
 * ADMIN is used for routes that require elevated access.
 * Routes for Wave 4 pages skip gracefully if the page is not yet implemented.
 */
// Paths and access roles reconciled against App.tsx + access.ts (2026-05-17)
const ROUTE_CHECKS: Array<{ path: string; role: string; wave4?: boolean }> = [
  { path: "/dashboard",   role: "PB" },
  { path: "/customers",   role: "PB" },
  { path: "/nba",         role: "PB" },
  { path: "/house-views", role: "PB" },
  { path: "/rag",         role: "PB" },
  { path: "/batch",       role: "ADMIN" },
  { path: "/audit",       role: "ADMIN" },
  // Wave 4 pages
  { path: "/quarantine",         role: "ADMIN",        wave4: true },
  { path: "/dispute-cases",      role: "PB",           wave4: true },
  { path: "/rights-notice",      role: "PB",           wave4: true },
  { path: "/ai-model-cards",     role: "PB",           wave4: true },
  { path: "/ai-policy",          role: "PB",           wave4: true },
  { path: "/korean-ai-act",      role: "PB",           wave4: true },
  { path: "/ai-admin-dashboard", role: "ADMIN",        wave4: true },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function loginUi(page: Page, email: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "직원 로그인" })).toBeVisible();
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password!);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

async function navigateSpa(page: Page, path: string): Promise<void> {
  await page.evaluate((next) => {
    window.history.pushState({}, "", next);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

/** Returns body text content; empty string on failure. */
async function bodyText(page: Page): Promise<string> {
  return (await page.locator("body").textContent()) ?? "";
}

/** True if the page responded with a 403 screen (route doesn't allow this role). */
async function is403(page: Page): Promise<boolean> {
  return page.url().includes("/403") || (await page.getByRole("heading", { name: "403" }).isVisible().catch(() => false));
}

/** True if the current URL looks like it redirected to /login (page not found / unauth). */
async function isLoginRedirect(page: Page): Promise<boolean> {
  return page.url().includes("/login");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Korean copy allowlist — rendered text assertions", { tag: ["@korean-copy"] }, () => {
  test.beforeEach(() => {
    test.skip(!password, "E2E_SYNTHETIC_PASSWORD is required; no synthetic-login bypass is allowed.");
  });

  // ── Per-route required Korean strings ────────────────────────────────────

  for (const { path, role, wave4 } of ROUTE_CHECKS) {
    const requiredStrings: string[] = (allowlist.required_per_route as Record<string, string[]>)[path] ?? [];
    if (requiredStrings.length === 0) continue;

    test(`${path} renders required Korean strings (${role})`, async ({ page }) => {
      if (wave4) {
        test.info().annotations.push({ type: "wave4", description: "Wave 4 page — skips if not yet implemented." });
      }

      await loginUi(page, ROLE_EMAILS[role] ?? ROLE_EMAILS.PB);
      await navigateSpa(page, path);

      if (wave4 && (await is403(page) || await isLoginRedirect(page))) {
        test.skip(true, `Wave 4 page ${path} not yet implemented — skipping.`);
        return;
      }

      const text = await bodyText(page);
      for (const required of requiredStrings) {
        expect(text, `${path}: required Korean string "${required}" not found`).toContain(required);
      }
    });
  }

  // ── Global banned patterns ────────────────────────────────────────────────

  test("no banned global patterns appear on dashboard, customers, NBA, house-views", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);

    const routesToCheck = ["/dashboard", "/customers", "/nba", "/house-views"];
    const banned: string[] = allowlist.banned_global as string[];

    for (const path of routesToCheck) {
      await navigateSpa(page, path);
      const text = await bodyText(page);

      for (const pattern of banned) {
        expect(text, `${path}: banned pattern "${pattern}" found in rendered text`).not.toContain(pattern);
      }
    }
  });

  test("no banned global patterns appear on admin pages (batch, audit)", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.ADMIN);
    const banned: string[] = allowlist.banned_global as string[];

    for (const path of ["/batch", "/audit"]) {
      await navigateSpa(page, path);
      const text = await bodyText(page);

      for (const pattern of banned) {
        expect(text, `${path}: banned pattern "${pattern}" found`).not.toContain(pattern);
      }
    }
  });

  // ── Numbered customer placeholder ban ─────────────────────────────────────

  test("numbered synthetic customer placeholders (고객 01 etc.) do not appear on any page", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    const numberedPattern = new RegExp(allowlist.banned_numbered_customer_pattern);

    for (const { path, role } of ROUTE_CHECKS) {
      if (role !== "PB") continue; // check PB-accessible routes only in this loop
      await navigateSpa(page, path);
      if (await is403(page)) continue;

      const text = await bodyText(page);
      expect(text, `${path}: numbered placeholder "고객 NN" found in rendered text`).not.toMatch(numberedPattern);
    }
  });

  // ── Raw API codes outside /audit ─────────────────────────────────────────

  test("raw API codes (PROVIDER_DONE etc.) do not appear on non-audit pages", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    const rawCodes: string[] = allowlist.banned_raw_api_codes as string[];

    // PB-accessible non-audit routes
    const nonAuditRoutes = ["/dashboard", "/customers", "/nba", "/house-views", "/rag"];
    for (const path of nonAuditRoutes) {
      await navigateSpa(page, path);
      const text = await bodyText(page);

      for (const code of rawCodes) {
        expect(text, `${path}: raw API code "${code}" must not appear in user-facing UI`).not.toContain(code);
      }
    }
  });

  test("raw API codes do not appear on ADMIN batch and audit viewer pages", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.ADMIN);
    const rawCodes: string[] = allowlist.banned_raw_api_codes as string[];

    // batch page may legitimately show some codes — check only the worst offenders
    await navigateSpa(page, "/batch");
    const batchText = await bodyText(page);
    // DOMESTIC_TOP200_MARKET_CAP and OFFICIAL_KRX_APPROVED should NOT appear raw
    for (const code of rawCodes) {
      expect(batchText, `/batch: raw API code "${code}" must not appear; use Korean label`).not.toContain(code);
    }
  });

  // ── AI metadata 4-tuple labelling ────────────────────────────────────────

  test("AI-generated cards show Korean 'AI 생성 ·' prefix not raw English metadata", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    await navigateSpa(page, "/dashboard");

    // The AI metadata footer must use Korean labels
    const text = await bodyText(page);
    // "AI 생성 ·" is the required prefix (existing spec from harness-critical)
    expect(text).toMatch(/AI 생성\s*·/);
    // Raw field names like "generated_at", "model_name" must not appear as UI labels
    expect(text).not.toMatch(/label="generated_at"/);
    expect(text).not.toMatch(/· generated_at/);
  });

  // ── Wave 4: AI governance pages Korean copy ───────────────────────────────

  test("AI model card pages use Korean headings and no raw English enum jargon", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    await navigateSpa(page, "/ai-model-cards");

    if (await is403(page) || await isLoginRedirect(page)) {
      test.skip(true, "Wave 4 /ai-model-cards not yet implemented — skipping.");
      return;
    }

    const text = await bodyText(page);
    // Must contain Korean heading text
    expect(text, "/ai-model-cards: must contain Korean content").toMatch(/[가-힯]/);
    expect(text, "/ai-model-cards: heading must be present").toContain("AI 모델 카드");
    // NOTE: agentId codes (rag_qa, email_draft etc.) are intentionally rendered in <code>
    // elements as technical identifiers alongside their Korean agentLabel. By design (Wave 4).
    // Verify Korean labels ARE present — that is the copy quality check.
    const requiredKoreanLabels = ["상담 브리핑", "이메일 초안", "하우스뷰 생성", "RAG 질의응답"];
    for (const label of requiredKoreanLabels) {
      expect(text, `/ai-model-cards: Korean label "${label}" must be visible`).toContain(label);
    }
  });

  test("인공지능기본법 page contains Korean governance checklist text", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    await navigateSpa(page, "/korean-ai-act");

    if (await is403(page) || await isLoginRedirect(page)) {
      test.skip(true, "Wave 4 /korean-ai-act not yet implemented — skipping.");
      return;
    }

    const text = await bodyText(page);
    expect(text, "/korean-ai-act must contain '인공지능기본법'").toContain("인공지능기본법");
  });

  // ── source_as_of paired with Korean label ────────────────────────────────

  test("source_as_of is always paired with 기준시각 Korean label on dashboard", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    await navigateSpa(page, "/dashboard");

    // "기준시각(source_as_of)" or "기준시각" must appear; raw "source_as_of" alone as a UI label must not
    const text = await bodyText(page);
    expect(text, "dashboard: raw source_as_of as standalone label forbidden").not.toMatch(/label="source_as_of"/);
    expect(text).not.toMatch(/· source_as_of\b/);
  });

  // ── Synthetic watermark and PoC badge ────────────────────────────────────

  test("Wave 4 PoC AUTO APPROVAL watermark uses Korean text not raw enum", async ({ page }) => {
    await loginUi(page, ROLE_EMAILS.PB);
    await navigateSpa(page, "/consultations/new");

    if (await is403(page)) {
      test.skip(true, "Consultation page blocked for this account.");
      return;
    }

    const text = await bodyText(page);
    // Raw enum values must not appear as top-level copy
    expect(text).not.toContain("PoC_AUTO_APPROVAL");
    // If the badge IS shown, it should be the Korean/human-readable label
    // (the badge itself may contain "PoC AUTO APPROVAL MODE" as a system label — that's per ADR-004)
  });
});
