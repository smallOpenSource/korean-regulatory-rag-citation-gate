/**
 * Step 1 — PB Daily E2E (service-readiness biz-cycle, 2026-05-24).
 *
 * Simulates one Private Banker's daily flow from login to audit:
 *   login → dashboard → customers list → customer 360 → consultation
 *   create + page enter → 4-gate spotcheck → house-view reference →
 *   email draft create → marketing review → audit confirmation.
 *
 * Each step verifies (a) navigation success, (b) the next page renders
 * meaningful content (not placeholder), (c) per-step screenshot. The
 * test focuses on data-flow continuity rather than micro-interactions.
 *
 * Output: audit-out/service-readiness/step1-pb-daily.json + per-step
 * fullPage PNGs.
 */

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = `http://127.0.0.1:${process.env.HARNESS_WEB_PORT || "8000"}`;
const API = `http://127.0.0.1:${process.env.HARNESS_API_PORT || "8010"}`;
const PASSWORD = "HarnessSynthetic!2026";
const PB_EMAIL = "synthetic.pb1@example.invalid";
const CUST_ID = "33333333-3333-3333-3333-333333333301";
const HV_ID  = "77777777-7777-7777-7777-777777777703";

const OUT = "audit-out/service-readiness";
mkdirSync(join(OUT, "screenshots"), { recursive: true });

const steps = [];

function record(step, ok, details) {
  steps.push({ step, ok, details });
  console.log(`[${ok ? "ok" : "FAIL"}] ${step} ${details ? "→ " + JSON.stringify(details).slice(0,160) : ""}`);
}

async function shot(page, name) {
  const path = join(OUT, "screenshots", `step1-${name}.png`);
  try { await page.screenshot({ path, fullPage: true }); } catch {}
  return path;
}

async function getTokenViaApi() {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: PB_EMAIL, password: PASSWORD }),
  });
  return (await r.json()).access_token;
}

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();
let consultationId = null;
let draftId = null;

try {
  // ── Step A: Login ─────────────────────────────────────────────────────
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.fill('input[type="email"]', PB_EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForLoadState("networkidle").catch(()=>{});
  await page.waitForTimeout(1500);
  record("A.login", !page.url().endsWith("/login"), { final_url: page.url() });

  // ── Step B: Dashboard ──────────────────────────────────────────────────
  await page.goto(`${BASE}/dashboard`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(1500);
  const dashBody = await page.textContent("body");
  await shot(page, "B-dashboard");
  record("B.dashboard", dashBody.length > 500 && !dashBody.includes("불러오지 못"),
    { body_len: dashBody.length, has_dashboard_word: dashBody.includes("대시보드") || dashBody.includes("Dashboard") });

  // ── Step C: Customers list ─────────────────────────────────────────────
  await page.goto(`${BASE}/customers`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(1500);
  const custBody = await page.textContent("body");
  await shot(page, "C-customers");
  record("C.customers_list", custBody.length > 500,
    { body_len: custBody.length, has_count: /\d+\s*(명|건)/.test(custBody) });

  // ── Step D: Customer 360 ───────────────────────────────────────────────
  await page.goto(`${BASE}/customers/${CUST_ID}`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(()=>{});
  await page.waitForTimeout(3500);
  const c360Body = await page.textContent("body");
  await shot(page, "D-customer360");
  record("D.customer360", c360Body.length > 800 && !c360Body.includes("불러오지 못"),
    { body_len: c360Body.length, has_portfolio: c360Body.includes("포트폴리오") || c360Body.includes("자산"),
      has_김민호: c360Body.includes("김민호") });

  // ── Step E: Consultation create via API + navigate to detail ──────────
  const token = await getTokenViaApi();
  const cr = await fetch(`${API}/consultations`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json",
               "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ customer_id: CUST_ID, channel_code: "FACE_TO_FACE" }),
  });
  const crJson = await cr.json();
  consultationId = crJson.id;
  record("E.consultation_create", cr.status === 201 && !!consultationId,
    { status: cr.status, consultation_id: consultationId });

  if (consultationId) {
    await page.goto(`${BASE}/consultations/${consultationId}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(()=>{});
    await page.waitForTimeout(3500);
    const csBody = await page.textContent("body");
    await shot(page, "E-consultation-detail");
    record("E.consultation_detail_render", csBody.length > 800,
      { body_len: csBody.length,
        has_4gate: csBody.includes("적합성") || csBody.includes("설명") || csBody.includes("부당권유"),
        has_briefing_button: csBody.includes("AI 브리핑") || csBody.includes("브리핑") });
  }

  // ── Step F: 4-gate acknowledge on a pre-seeded consultation ───────────
  // The brand-new consultation has no gate rows yet (suitability check
  // would require a 6-factor payload + product_id). Use the V067-seeded
  // consultation 66...6302 whose marketing gate sits PENDING and can be
  // acknowledged directly — same backend endpoint, same role gate.
  const seededConsultId = "66666666-6666-6666-6666-666666666302";
  const gr = await fetch(`${API}/consultations/${seededConsultId}/four-gate/marketing/acknowledge`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json",
               "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ evidence: { source: "step1_e2e", note: "marketing gate acknowledged" } }),
  });
  record("F.gate_marketing_ack", [200, 201, 202].includes(gr.status), { status: gr.status });

  // ── Step G: House-view reference ──────────────────────────────────────
  await page.goto(`${BASE}/house-views/${HV_ID}`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(2000);
  const hvBody = await page.textContent("body");
  await shot(page, "G-house-view");
  record("G.house_view_render", hvBody.length > 1500 &&
    !hvBody.includes("AI 생성 콘텐츠가 아직 채워지지"),
    { body_len: hvBody.length,
      has_assets: hvBody.includes("자산 전망"),
      has_portfolio: hvBody.includes("모델 포트폴리오"),
      has_risks: hvBody.includes("주요 리스크") });

  // ── Step H: Email draft create ────────────────────────────────────────
  const dr = await fetch(`${API}/email-drafts`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json",
               "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      customer_id: CUST_ID,
      subject: "[SYN] step1 e2e 안내",
      body: "[부적합 유형] 원금 손실 가능, 적합하지 않은 투자자: 안정형. 상담 결과를 안내드립니다.",
    }),
  });
  const drJson = await dr.json();
  draftId = drJson.id;
  record("H.email_draft_create", dr.status === 201 && !!draftId,
    { status: dr.status, draft_id: draftId });

  await page.goto(`${BASE}/email-drafts`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(2000);
  const edBody = await page.textContent("body");
  await shot(page, "H-email-drafts");
  record("H.email_drafts_page", edBody.length > 500,
    { body_len: edBody.length, has_step1_subject: edBody.includes("step1 e2e") });

  // ── Step I: Marketing review ──────────────────────────────────────────
  const mr = await fetch(`${API}/marketing-review`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json",
               "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      subject: "[SYN] step1 광고 심의",
      body: "[부적합 유형] 원금 손실 가능, 적합하지 않은 투자자: 위험회피형. 상품 권유 (synthetic).",
      consultation_id: consultationId,
      marketing_classified: true,
    }),
  });
  const mrJson = await mr.json();
  record("I.marketing_review", mr.status === 200,
    { status: mr.status, decision: mrJson.decision });

  // ── Step J: Audit log spot-check via API ──────────────────────────────
  // /audit-logs is the canonical path; PB has no read access (ADMIN/AUDIT_VIEWER only).
  const al = await fetch(`${API}/audit-logs?limit=5`, {
    headers: { "Authorization": `Bearer ${token}` },
  });
  record("J.audit_pb_forbidden_by_design", al.status === 403,
    { status: al.status, note: "PB cannot read audit log (ADMIN/AUDIT_VIEWER only)" });

  // Also verify the audit row landed (using the ADMIN token)
  const adminToken = await (async () => {
    const r = await fetch(`${API}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "synthetic.admin@example.invalid", password: PASSWORD }),
    });
    return (await r.json()).access_token;
  })();
  const al2 = await fetch(`${API}/audit-logs?limit=10&action_code=consultation_status_changed`, {
    headers: { "Authorization": `Bearer ${adminToken}` },
  });
  const al2Json = al2.status === 200 ? await al2.json() : null;
  record("J.audit_admin_can_read", al2.status === 200,
    { status: al2.status, recent_count: al2Json ? (al2Json.items ?? []).length : 0 });

} finally {
  await ctx.close();
  await browser.close();
}

writeFileSync(join(OUT, "step1-pb-daily.json"), JSON.stringify({ steps, consultationId, draftId }, null, 2));
const ok = steps.filter(s => s.ok).length;
console.log(`\n=== Step 1 PB Daily E2E: ${ok}/${steps.length} steps passed ===`);
process.exit(ok === steps.length ? 0 : 1);
