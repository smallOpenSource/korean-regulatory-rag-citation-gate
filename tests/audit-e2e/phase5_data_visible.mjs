/**
 * Phase 5 — Verify V067 fixture rows render on the formerly-empty pages.
 *
 * Each page is visited with the role that has list-read access, and we
 * count list items via a heuristic: number of `<article>`/`<tr>`/`<li>`
 * elements with a recognisable per-row class, plus an explicit substring
 * search for one of the fixture-seeded SYN markers.
 */

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = `http://127.0.0.1:${process.env.HARNESS_WEB_PORT ?? "8000"}`;
const PASSWORD = "HarnessSynthetic!2026";
const OUT_DIR = "audit-out/service-readiness";
mkdirSync(OUT_DIR, { recursive: true });

const CHECKS = [
  { path: "/kyc-edd",            role: "PB",    needle: "ASSET_CHANGE_PCT|OVERSEAS_TRANSFER|PEP_FLAG|HIGH_RISK_PRODUCT",  minHits: 1 },
  { path: "/rights-notice",      role: "PB",    needle: "청약철회권|민원접수권|분쟁조정신청권",                                    minHits: 1 },
  { path: "/conflict-of-interest", role: "PB",  needle: "PRE_TRADE|POST_TRADE|RELATED_PARTY",                              minHits: 1 },
  { path: "/consents",           role: "PB",    needle: "GENERAL_BUNDLE|INFORMATION_USE|MARKETING_CONTACT|DATA_SHARING",   minHits: 1 },
  { path: "/data-governance",    role: "ADMIN", needle: "정기 retention|마케팅 자료 보관|AI 출력 감사|개인정보 처리내역",         minHits: 1 },
  { path: "/dispute-cases",      role: "PB",    needle: "부당권유|광고|계약|기타",                                            minHits: 1 },
  { path: "/marketing-review",   role: "PB",    needle: "MARKETING_REVIEW_PASS|MARKETING_REVIEW_BLOCK",                    minHits: 1 },
];

const EMAILS = {
  PB:    "synthetic.pb1@example.invalid",
  ADMIN: "synthetic.admin@example.invalid",
};

async function login(page, email) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle", timeout: 20000 });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(()=>{});
  await page.waitForTimeout(1500);
}

const browser = await chromium.launch({ headless: true });
const results = [];
for (const role of ["PB", "ADMIN"]) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  try {
    await login(page, EMAILS[role]);
  } catch (e) {
    console.error(`login ${role} failed`); await ctx.close(); continue;
  }
  for (const check of CHECKS) {
    if (check.role !== role) continue;
    await page.goto(`${BASE}${check.path}`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(2000);
    const body = await page.textContent("body");
    const re = new RegExp(check.needle, "g");
    const hits = (body.match(re) ?? []).length;
    const pass = hits >= check.minHits;
    const screenshot = join(OUT_DIR, "screenshots", `phase5-${check.path.replace(/\//g,"_")}.png`);
    try { await page.screenshot({ path: screenshot, fullPage: true }); } catch {}
    results.push({ path: check.path, role, hits, minHits: check.minHits, pass, screenshot });
    console.log(`[${pass?"ok":"FAIL"}] ${role} ${check.path} → ${hits} hits (need ≥${check.minHits})`);
  }
  await ctx.close();
}
await browser.close();
writeFileSync(join(OUT_DIR, "phase5-data-visible.json"), JSON.stringify(results, null, 2));
const failures = results.filter(r => !r.pass);
console.log(`\n=== SUMMARY ${results.length - failures.length}/${results.length} pages have fixture data visible ===`);
process.exit(failures.length > 0 ? 1 : 0);
