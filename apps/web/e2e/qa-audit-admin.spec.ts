/**
 * qa-audit-admin.spec.ts — capture ADMIN-only and detail pages.
 *
 * Logs in as the synthetic ADMIN user and navigates to admin-restricted
 * routes + detail routes that aren't reachable in the PB-role qa-audit.
 */
import { expect, test } from "@playwright/test";
import * as fs from "node:fs";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const ARTIFACT_DIR = "qa-audit-out";

const ADMIN_ROUTES = [
  "/batch",
  "/audit",
  "/audit-viewer",
  "/quarantine",
  "/ai-admin-dashboard",
];

test.beforeAll(() => {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
});

async function loginAsAdmin(page: import("@playwright/test").Page): Promise<void> {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
    const emailInput = page.locator('input[type=email], input[name=email]').first();
    if ((await emailInput.count().catch(() => 0)) === 0) {
      return;
    }
    await emailInput.fill("synthetic.admin@example.invalid");
    await page
      .locator('input[type=password], input[name=password]')
      .first()
      .fill("HarnessSynthetic!2026");
    await page
      .locator('button[type=submit], button:has-text("로그인")')
      .first()
      .click()
      .catch(() => null);
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
    await page
      .waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 4000 })
      .catch(() => null);
    if (!page.url().endsWith("/login")) {
      return;
    }
    await page.waitForTimeout(500);
  }
}

for (const url of ADMIN_ROUTES) {
  test(`@qa-audit-admin ${url}`, async ({ page }) => {
    await loginAsAdmin(page);
    const resp = await page.goto(`${BASE_URL}${url}`, { waitUntil: "load" }).catch(() => null);
    test.skip(resp === null, "Frontend dev server unreachable");
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
    const slug = `admin_${url.replace(/\W+/g, "_").replace(/^_|_$/g, "")}`;
    const text = (await page.textContent("body").catch(() => "")) ?? "";
    fs.writeFileSync(`${ARTIFACT_DIR}/${slug}.txt`, text, "utf-8");
    await page.screenshot({ path: `${ARTIFACT_DIR}/${slug}.png`, fullPage: true }).catch(() => null);
    expect(text.length).toBeGreaterThan(0);
  });
}

// Detail / dynamic routes (PB role can also reach customer 360 + house-view detail)
async function loginAsPB(page: import("@playwright/test").Page): Promise<void> {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
    const emailInput = page.locator('input[type=email], input[name=email]').first();
    if ((await emailInput.count().catch(() => 0)) === 0) {
      return;
    }
    await emailInput.fill("synthetic.pb1@example.invalid");
    await page.locator('input[type=password], input[name=password]').first().fill("HarnessSynthetic!2026");
    await page.locator('button[type=submit], button:has-text("로그인")').first().click().catch(() => null);
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
    await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 4000 }).catch(() => null);
    if (!page.url().endsWith("/login")) {
      return;
    }
    await page.waitForTimeout(500);
  }
}

test("@qa-audit-admin /customers/{first} (Customer 360 — PB)", async ({ page }) => {
  await loginAsPB(page);
  // Navigate to customers list first to read out a real customer id
  await page.goto(`${BASE_URL}/customers`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
  const linkHref = await page
    .locator('a[href^="/customers/"]')
    .first()
    .getAttribute("href")
    .catch(() => null);
  test.skip(!linkHref || linkHref === "/customers", "No customer link found");
  await page.goto(`${BASE_URL}${linkHref}`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
  const text = (await page.textContent("body").catch(() => "")) ?? "";
  fs.writeFileSync(`${ARTIFACT_DIR}/admin_customer360.txt`, text, "utf-8");
  await page.screenshot({ path: `${ARTIFACT_DIR}/admin_customer360.png`, fullPage: true }).catch(() => null);
  expect(text.length).toBeGreaterThan(0);
});

test("@qa-audit-admin /house-views/{first} (House View detail)", async ({ page }) => {
  await loginAsPB(page);
  await page.goto(`${BASE_URL}/house-views`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
  const linkHref = await page
    .locator('a[href^="/house-views/"]')
    .first()
    .getAttribute("href")
    .catch(() => null);
  test.skip(!linkHref || linkHref === "/house-views", "No house-view link found");
  await page.goto(`${BASE_URL}${linkHref}`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
  const text = (await page.textContent("body").catch(() => "")) ?? "";
  fs.writeFileSync(`${ARTIFACT_DIR}/admin_houseview_detail.txt`, text, "utf-8");
  await page.screenshot({ path: `${ARTIFACT_DIR}/admin_houseview_detail.png`, fullPage: true }).catch(() => null);
  expect(text.length).toBeGreaterThan(0);
});
