/**
 * Phase 1 Systematic Page × Role Walkthrough (Service Readiness v2)
 *
 * Visits every UI route as each of 5 roles, records access outcome
 * (allowed render vs 403/redirect), placeholder/error hits, and
 * screenshots. Output → audit-out/service-readiness/phase1.json plus
 * per-scenario PNGs.
 *
 * Run: cd tests/audit-e2e && DISPLAY=:99 node phase1_walkthrough.mjs
 */

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.AUDIT_BASE_URL ?? `http://127.0.0.1:${process.env.HARNESS_WEB_PORT ?? 8000}`;
const PASSWORD = "HarnessSynthetic!2026";
const OUT_DIR = "audit-out/service-readiness";
mkdirSync(OUT_DIR, { recursive: true });
mkdirSync(join(OUT_DIR, "screenshots"), { recursive: true });

const ROLES = [
  { code: "PB",             email: "synthetic.pb1@example.invalid" },
  { code: "WM",             email: "synthetic.wm1@example.invalid" },
  { code: "BRANCH_MANAGER", email: "synthetic.branch.manager@example.invalid" },
  { code: "ADMIN",          email: "synthetic.admin@example.invalid" },
  { code: "AUDIT_VIEWER",   email: "synthetic.audit@example.invalid" },
];

const HV_ID = "77777777-7777-7777-7777-777777777703";
const CUST_ID = "33333333-3333-3333-3333-333333333f01";
const CONS_ID = "d76eadb9-bc84-49e2-ad9f-8c18e9a148d0";

const ROUTES = [
  { key: "dashboard",          path: "/dashboard",                                              allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "customers",          path: "/customers",                                              allowed: ["PB","WM","BRANCH_MANAGER","ADMIN"] },
  { key: "customer360",        path: `/customers/${CUST_ID}`,                                   allowed: ["PB","WM","BRANCH_MANAGER","ADMIN"] },
  { key: "consultation",       path: `/consultations/${CONS_ID}`,                               allowed: ["PB","WM"] },
  { key: "nba",                path: "/nba",                                                    allowed: ["PB","WM"] },
  { key: "aftercare",          path: "/aftercare",                                              allowed: ["PB","WM","BRANCH_MANAGER","ADMIN"] },
  { key: "emailDrafts",        path: "/email-drafts",                                           allowed: ["PB","WM"] },
  { key: "houseViews",         path: "/house-views",                                            allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "houseViewDetail",    path: `/house-views/${HV_ID}`,                                   allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "houseViewActivate",  path: `/house-views/${HV_ID}/activate`,                          allowed: ["ADMIN"] },
  { key: "rag",                path: "/rag",                                                    allowed: ["PB","WM","BRANCH_MANAGER","ADMIN"] },
  { key: "batch",              path: "/batch",                                                  allowed: ["ADMIN"] },
  { key: "audit",              path: "/audit",                                                  allowed: ["ADMIN","AUDIT_VIEWER"] },
  { key: "auditViewer",        path: "/audit-viewer",                                           allowed: ["ADMIN","AUDIT_VIEWER"] },
  { key: "quarantine",         path: "/quarantine",                                             allowed: ["ADMIN"] },
  { key: "rightsNotice",       path: "/rights-notice",                                          allowed: ["PB","WM","BRANCH_MANAGER","ADMIN"] },
  { key: "disputeCase",        path: "/dispute-cases",                                          allowed: ["PB","WM","ADMIN","AUDIT_VIEWER"] },
  { key: "conflictOfInterest", path: "/conflict-of-interest",                                   allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "marketingReview",    path: "/marketing-review",                                       allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "dataGovernance",     path: "/data-governance",                                        allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "consents",           path: "/consents",                                               allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "kycEdd",             path: "/kyc-edd",                                                allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "aiModelCards",       path: "/ai-model-cards",                                         allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "aiPolicy",           path: "/ai-policy",                                              allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "koreanAIAct",        path: "/korean-ai-act",                                          allowed: ["PB","WM","BRANCH_MANAGER","ADMIN","AUDIT_VIEWER"] },
  { key: "aiAdminDashboard",   path: "/ai-admin-dashboard",                                     allowed: ["ADMIN"] },
  { key: "autopilotDemo",      path: "/autopilot-demo",                                         allowed: ["PB","WM","BRANCH_MANAGER","ADMIN"] },
];

const PLACEHOLDER_RE = /AI 생성 콘텐츠가 아직|정보 없음|기재 없음|불러오지 못했습니다|데이터를 불러오지 못/g;
const ERROR_RE = /오류가 발생|에러|실패|불러오는 데 실패/g;

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

async function visit(page, route, roleCode) {
  const start = Date.now();
  let finalURL = "";
  let httpStatus = 0;
  let bodyLen = 0;
  let placeholderHits = 0;
  let errorHits = 0;
  let exception = null;
  try {
    const resp = await page.goto(`${BASE}${route.path}`, { waitUntil: "networkidle", timeout: 20000 });
    httpStatus = resp ? resp.status() : 0;
    await page.waitForTimeout(1500);
    finalURL = page.url();
    const body = await page.textContent("body");
    bodyLen = body.length;
    placeholderHits = (body.match(PLACEHOLDER_RE) ?? []).length;
    errorHits = (body.match(ERROR_RE) ?? []).length;
  } catch (e) {
    exception = String(e).slice(0, 200);
    finalURL = page.url();
  }

  const expectedAllowed = route.allowed.includes(roleCode);
  const landedOn403 = finalURL.endsWith("/403") || finalURL.includes("/403?");
  const landedOnLogin = finalURL.endsWith("/login");
  // Final verdict
  const intendedRender = finalURL.includes(route.path.split("?")[0]) && !landedOn403 && !landedOnLogin;
  const accessExpectationMet = expectedAllowed ? intendedRender : (landedOn403 || landedOnLogin || !intendedRender);

  const screenshot = join(OUT_DIR, "screenshots", `${route.key}-${roleCode}.png`);
  try { await page.screenshot({ path: screenshot, fullPage: false }); } catch {}

  return {
    routeKey: route.key,
    routePath: route.path,
    role: roleCode,
    expectedAllowed,
    httpStatus,
    finalURL,
    intendedRender,
    landedOn403,
    landedOnLogin,
    accessExpectationMet,
    bodyLen,
    placeholderHits,
    errorHits,
    exception,
    elapsed_ms: Date.now() - start,
    screenshot,
  };
}

const browser = await chromium.launch({ headless: true });
const results = [];

for (const role of ROLES) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await login(page, role.email);
  } catch (e) {
    console.error(`[fail] login ${role.code}: ${e}`);
    await context.close();
    continue;
  }
  for (const route of ROUTES) {
    const r = await visit(page, route, role.code);
    results.push(r);
    const tag = r.accessExpectationMet ? "ok" : "MISMATCH";
    console.log(`[${tag}] ${role.code} ${route.key} → http=${r.httpStatus} url=${r.finalURL.replace(BASE,"")} ph=${r.placeholderHits} err=${r.errorHits}`);
  }
  await context.close();
}
await browser.close();

writeFileSync(join(OUT_DIR, "phase1-walkthrough.json"), JSON.stringify(results, null, 2));

// Summary
const total = results.length;
const accessOK = results.filter(r => r.accessExpectationMet).length;
const accessMismatch = results.filter(r => !r.accessExpectationMet);
const phHit = results.filter(r => r.expectedAllowed && r.placeholderHits > 0);
const errHit = results.filter(r => r.expectedAllowed && r.errorHits > 0);

console.log("\n=== SUMMARY ===");
console.log(`scenarios:      ${total}`);
console.log(`access ok:      ${accessOK}/${total}`);
console.log(`access mismatch: ${accessMismatch.length}`);
console.log(`placeholder hits (allowed): ${phHit.length} scenarios`);
console.log(`error hits (allowed): ${errHit.length} scenarios`);
if (accessMismatch.length > 0) {
  console.log("\nMismatches:");
  for (const m of accessMismatch.slice(0, 10)) {
    console.log(`  ${m.role} ${m.routeKey}: expected=${m.expectedAllowed?"allowed":"forbidden"}, actual_url=${m.finalURL.replace(BASE,"")}`);
  }
}
if (phHit.length > 0) {
  console.log("\nPlaceholder hits:");
  for (const r of phHit.slice(0, 20)) {
    console.log(`  ${r.role} ${r.routeKey}: ${r.placeholderHits} hits`);
  }
}
if (errHit.length > 0) {
  console.log("\nError-text hits:");
  for (const r of errHit.slice(0, 20)) {
    console.log(`  ${r.role} ${r.routeKey}: ${r.errorHits} hits`);
  }
}
process.exit(accessMismatch.length + phHit.length + errHit.length > 0 ? 1 : 0);
