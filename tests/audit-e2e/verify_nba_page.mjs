import { chromium } from "@playwright/test";

const BASE = `http://127.0.0.1:${process.env.HARNESS_WEB_PORT ?? "8000"}`;
const PASSWORD = "HarnessSynthetic!2026";

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();

try {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle", timeout: 20000 });
  await page.fill('input[type="email"]', "synthetic.pb1@example.invalid");
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(()=>{});
  await page.waitForTimeout(1500);

  await page.goto(`${BASE}/nba`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2500);

  const body = await page.textContent("body");
  const hasScriptToggle = body.includes("AI 스크립트 보기");
  const hasEmptyState = body.includes("대기 중인 NBA 카드가 없습니다");
  const placeholderHits = (body.match(/AI 생성 콘텐츠가 아직 채워지지 않았습니다/g) ?? []).length;

  await page.screenshot({ path: "/tmp/nba-page-after-w3.png", fullPage: true });

  console.log(JSON.stringify({
    url: page.url(),
    hasScriptToggle,
    hasEmptyState,
    placeholderHits,
    bodyLength: body.length,
  }, null, 2));
} finally {
  await ctx.close();
  await browser.close();
}
