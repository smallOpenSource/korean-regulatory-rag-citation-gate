import { chromium } from "@playwright/test";

const BASE = `http://127.0.0.1:${process.env.HARNESS_WEB_PORT || 8000}`;
const PASSWORD = "HarnessSynthetic!2026";

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const consoleLogs = [];
const pageErrors = [];
page.on("console", (msg) => consoleLogs.push({ type: msg.type(), text: msg.text() }));
page.on("pageerror", (err) => pageErrors.push(err.message));

try {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle", timeout: 20000 });
  await page.fill('input[type="email"]', "synthetic.admin@example.invalid");
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForTimeout(1500);

  await page.goto(`${BASE}/data-governance`, { waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(3000);
  const body = await page.textContent("body");
  const html = await page.content();
  console.log(JSON.stringify({
    url: page.url(),
    bodyLength: body.length,
    bodyFirst200: body.slice(0, 200),
    htmlLength: html.length,
    pageErrors,
    consoleErrors: consoleLogs.filter(l => l.type === "error").slice(0, 10),
    consoleWarnings: consoleLogs.filter(l => l.type === "warning").slice(0, 5),
  }, null, 2));
} finally {
  await ctx.close(); await browser.close();
}
