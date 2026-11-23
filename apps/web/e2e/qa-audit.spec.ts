/**
 * QA audit — captures rendered Korean copy + screenshots from key pages.
 */
import { expect, test } from "@playwright/test";
import * as fs from "node:fs";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:4173";
const ARTIFACT_DIR = "qa-audit-out";

const PAGES = [
  "/dashboard", "/customers", "/consultations/SYN-CUST-001", "/nba", "/aftercare",
  "/house-views", "/rag", "/quarantine", "/email-drafts", "/audit",
  "/dispute-cases", "/rights-notice", "/ai-model-cards", "/ai-policy",
  "/korean-ai-act", "/ai-admin-dashboard",
];

test.beforeAll(() => {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
});

for (const url of PAGES) {
  test(`@qa-audit ${url}`, async ({ page }) => {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
    const emailInput = page.locator('input[type=email], input[name=email]').first();
    if ((await emailInput.count().catch(() => 0)) > 0) {
      await emailInput.fill("synthetic.pb1@example.invalid");
      await page.locator('input[type=password], input[name=password]').first().fill("HarnessSynthetic!2026");
      await page.locator('button[type=submit], button:has-text("로그인")').first().click().catch(() => null);
      await page.waitForLoadState("networkidle").catch(() => null);
    }
    const resp = await page.goto(`${BASE_URL}${url}`, { waitUntil: "load" }).catch(() => null);
    test.skip(resp === null, "Frontend dev server unreachable");
    await page.waitForLoadState("networkidle").catch(() => null);
    const slug = url.replace(/\W+/g, "_").replace(/^_|_$/g, "") || "root";
    const text = (await page.textContent("body").catch(() => "")) ?? "";
    fs.writeFileSync(`${ARTIFACT_DIR}/${slug}.txt`, text, "utf-8");
    await page.screenshot({ path: `${ARTIFACT_DIR}/${slug}.png`, fullPage: true }).catch(() => null);
    expect(text.length).toBeGreaterThan(0);
  });
}
