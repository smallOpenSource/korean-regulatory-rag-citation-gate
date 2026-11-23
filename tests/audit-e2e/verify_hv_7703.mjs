import { chromium } from "@playwright/test";

const BASE = `http://127.0.0.1:${process.env.HARNESS_WEB_PORT || 8000}`;
const HV_ID = "77777777-7777-7777-7777-777777777703";
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

  await page.goto(`${BASE}/house-views/${HV_ID}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2500);

  const body = await page.textContent("body");
  const hasPlaceholder = body.includes("AI 생성 콘텐츠가 아직 채워지지 않았습니다");
  const hasAssetView = body.includes("자산 전망");
  const hasPortfolio = body.includes("모델 포트폴리오");
  const hasRisks = body.includes("주요 리스크");
  const contentSignals = [
    body.includes("코스피") || body.includes("KOSPI"),
    body.includes("미연준") || body.includes("연준"),
    body.includes("주식") && body.includes("채권"),
    body.includes("안정형") || body.includes("성장형"),
  ];
  const populated = contentSignals.filter(Boolean).length;

  const screenshotPath = "/tmp/hv-7703-after-w3.png";
  await page.screenshot({ path: screenshotPath, fullPage: true });

  console.log(JSON.stringify({
    url: page.url(),
    hasPlaceholder,
    hasAssetView,
    hasPortfolio,
    hasRisks,
    contentSignalsHit: populated,
    bodyLength: body.length,
    screenshot: screenshotPath,
  }, null, 2));
} finally {
  await ctx.close();
  await browser.close();
}
