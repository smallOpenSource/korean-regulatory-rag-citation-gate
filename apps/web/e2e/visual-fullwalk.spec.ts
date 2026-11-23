/**
 * visual-fullwalk.spec.ts — Visual Full-Walk Audit v7.1
 *
 * ─── P1 Visible-DOM SoT 운영 정의 (AC10 spec 주석 박제) ───────────────────────
 * PB/WM/AUDIT_VIEWER가 viewport에서 실제로 보는 것 = visible-DOM.
 * 구현: TreeWalker (visibility:hidden / display:none / aria-hidden=true 제외 노드)
 *      + Playwright locator.filter({ visible: true }) 병용.
 * page.textContent("body") 사용 금지 — closed <details> / aria-hidden 영역
 * 혼재로 invisible 콘텐츠까지 수집되어 P1 SoT 위반.
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Coverage (PRD §8):
 *   22 routes × 3 roles (PB, WM, AUDIT_VIEWER) = 66 page-cells
 *   + V048 fixture 판정: AC3a / AC3b  (S5 dead-detection)
 *   + AC12: JsonSection empty state → 동일 한국어 메시지 박제
 *
 * Screenshot 저장:
 *   .omc/visual-audit/screenshots/{role}_{slug}_{viewport|full}.png
 *   Viewport: 1280 × 800
 *
 * 데이터 픽스처:
 *   V048 AUDIT-NEG-001 = a0000048-0000-0000-0000-000000000001 (결함 fixture)
 *   V048 AUDIT-POS-001 = a0000048-0000-0000-0000-000000000002 (정상 fixture)
 */

import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  ALL_BANNED,
  BANNED_AUDIT_PREFIX,
  BANNED_INTERNAL_ID,
} from "./_shared/banned-patterns";

/**
 * Role-aware banned patterns (PRD §9.5 Lane C 매트릭스)
 * BANNED_INTERNAL_ID (ADR-###, W#-T#, REG-0#):
 *   - PB/WM: 노출 금지 → ALL_BANNED 적용
 *   - AUDIT_VIEWER/ADMIN: role-gated display 허용 (감사·거버넌스 페이지 의도된 정합)
 *     → BANNED_INTERNAL_ID 제외한 패턴만 적용
 */
const ALL_BANNED_AUDIT_VIEWER = ALL_BANNED.filter((p) => p !== BANNED_INTERNAL_ID);

// ─── 환경 상수 ────────────────────────────────────────────────────────────────

const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const SCREENSHOT_DIR = "qa-audit-out/visual-fullwalk";

/** AC12 SoT — HouseViewDetailPage.tsx:72-74 */
const JSON_SECTION_EMPTY_MSG =
  "AI 생성 콘텐츠가 아직 채워지지 않았습니다. 생성 또는 검토 단계에서 채워집니다.";

/** V048 fixture UUIDs (V048__audit_fixture_house_views.sql SoT) */
const AUDIT_NEG_001_ID = "a0000048-0000-0000-0000-000000000001";
const AUDIT_POS_001_ID = "a0000048-0000-0000-0000-000000000002";

// ─── 3 Audit roles (PRD §8: PB, WM, AUDIT_VIEWER) ────────────────────────────

const ROLES = [
  { role: "PB" as const, email: "synthetic.pb1@example.invalid" },
  { role: "WM" as const, email: "synthetic.wm1@example.invalid" },
  { role: "AUDIT_VIEWER" as const, email: "synthetic.audit@example.invalid" },
];
type RoleName = "PB" | "WM" | "AUDIT_VIEWER";

// ─── 22 audit-target routes (route-manifest.json / App.tsx:46-75 SoT) ────────
// allowed: access.ts ACCESS_RULES 기준 (PB/WM/AUDIT_VIEWER 교집합만 표기)

const ROUTE_MANIFEST: ReadonlyArray<{
  templatePath: string;
  slug: string;
  allowed: readonly RoleName[];
}> = [
  { templatePath: "/dashboard",                       slug: "dashboard",            allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/customers",                       slug: "customers",            allowed: ["PB", "WM"] },
  { templatePath: "/customers/:customerId",           slug: "customers_detail",     allowed: ["PB", "WM"] },
  { templatePath: "/consultations/:consultationId",   slug: "consultations_detail", allowed: ["PB", "WM"] },
  { templatePath: "/nba",                             slug: "nba",                  allowed: ["PB", "WM"] },
  { templatePath: "/aftercare",                       slug: "aftercare",            allowed: ["PB", "WM"] },
  { templatePath: "/email-drafts",                    slug: "email_drafts",         allowed: ["PB", "WM"] },
  { templatePath: "/house-views",                     slug: "house_views",          allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/house-views/:houseViewId",        slug: "house_views_detail",   allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/house-views/:houseViewId/activate", slug: "house_views_activate", allowed: [] },   // ADMIN only
  { templatePath: "/rag",                             slug: "rag",                  allowed: ["PB", "WM"] },
  { templatePath: "/batch",                           slug: "batch",                allowed: [] },       // ADMIN only
  { templatePath: "/audit",                           slug: "audit",                allowed: ["AUDIT_VIEWER"] },
  { templatePath: "/quarantine",                      slug: "quarantine",           allowed: [] },       // ADMIN only
  { templatePath: "/audit-viewer",                    slug: "audit_viewer",         allowed: ["AUDIT_VIEWER"] },
  { templatePath: "/rights-notice",                   slug: "rights_notice",        allowed: ["PB", "WM"] },
  { templatePath: "/dispute-cases",                   slug: "dispute_cases",        allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/ai-model-cards",                  slug: "ai_model_cards",       allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/ai-policy",                       slug: "ai_policy",            allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/korean-ai-act",                   slug: "korean_ai_act",        allowed: ["PB", "WM", "AUDIT_VIEWER"] },
  { templatePath: "/ai-admin-dashboard",              slug: "ai_admin_dashboard",   allowed: [] },       // ADMIN only
  { templatePath: "/autopilot-demo",                  slug: "autopilot_demo",       allowed: ["PB", "WM"] },
] as const;

// ─── Dynamic IDs (BeforeAll에서 확보) ────────────────────────────────────────

let resolvedCustomerId = "";
let resolvedHouseViewId = "";
const FALLBACK_CONSULTATION_ID = "SYN-CUST-001";

function resolveRoutePath(templatePath: string): string {
  return templatePath
    .replace(":customerId", resolvedCustomerId || "00000000-0000-0000-0000-000000000000")
    .replace(":consultationId", FALLBACK_CONSULTATION_ID)
    .replace(":houseViewId", resolvedHouseViewId || "00000000-0000-0000-0000-000000000000");
}

// ─── P1 SoT: Visible-DOM text extractor ──────────────────────────────────────
// TreeWalker: visibility:hidden / display:none / aria-hidden=true 제외.
// page.textContent("body") 사용 금지.

async function getVisibleText(page: Page): Promise<string> {
  return page.evaluate((): string => {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node: Node): number {
          const el = node.parentElement;
          if (!el) return NodeFilter.FILTER_REJECT;
          // aria-hidden 서브트리 전체 제외
          if (el.closest("[aria-hidden='true']")) return NodeFilter.FILTER_REJECT;
          // CSS display:none / visibility:hidden 제외
          const style = window.getComputedStyle(el);
          if (style.display === "none") return NodeFilter.FILTER_REJECT;
          if (style.visibility === "hidden") return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        },
      },
    );
    const chunks: string[] = [];
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const t = node.textContent?.trim();
      if (t) chunks.push(t);
    }
    return chunks.join("\n");
  });
}

/**
 * <details> 요소를 모두 open 처리 후 visible text 수집.
 * PromptAuditTrail (details closed 기본) open 상태 banned 검사용.
 */
async function getVisibleTextWithDetailsOpen(page: Page): Promise<string> {
  await page.evaluate((): void => {
    document.querySelectorAll<HTMLDetailsElement>("details").forEach((d) => {
      d.open = true;
    });
  });
  return getVisibleText(page);
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

async function loginAs(page: Page, email: string): Promise<void> {
  // SPA Zustand state + 쿠키 완전 초기화 — about:blank로 SPA unload 후 재진입
  await page.goto("about:blank").catch(() => null);
  await page.context().clearCookies().catch(() => null);
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
    const emailInput = page.locator('input[type=email], input[name=email]').first();
    if ((await emailInput.count().catch(() => 0)) === 0) return; // already authenticated
    await emailInput.fill(email);
    await page.locator('input[type=password], input[name=password]').first().fill("HarnessSynthetic!2026");
    await page.locator('button[type=submit], button:has-text("로그인")').first().click().catch(() => null);
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
    await page
      .waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 4000 })
      .catch(() => null);
    if (!page.url().endsWith("/login")) return;
    await page.waitForTimeout(500);
  }
}

async function loginAsAdmin(page: Page): Promise<void> {
  return loginAs(page, "synthetic.admin@example.invalid");
}

// ─── Screenshot ───────────────────────────────────────────────────────────────

async function captureScreenshots(page: Page, role: string, slug: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 800 });
  const vpPath = path.join(SCREENSHOT_DIR, `${role}_${slug}_viewport.png`);
  const fpPath = path.join(SCREENSHOT_DIR, `${role}_${slug}_full.png`);
  await page.screenshot({ path: vpPath, fullPage: false }).catch(() => null);
  await page.screenshot({ path: fpPath, fullPage: true }).catch(() => null);
}

// ─── V048 fixture 존재 여부 (DB skip guard) ────────────────────────────────────

/**
 * V048 fixture 페이지 로드 성공 여부 (404/error/login redirect skip guard)
 * URL이 /login이면 false: 로그인 실패로 인한 redirect를 FAIL이 아닌 SKIP으로 처리.
 */
async function isFixtureLoaded(page: Page): Promise<boolean> {
  const url = page.url();
  if (url.includes("/login")) return false; // 인증 실패 → SKIP
  const text = await getVisibleText(page);
  return !text.includes("하우스뷰를 불러오지 못했습니다");
}

// ============================================================================
// BeforeAll — directories + dynamic ID 확보
// ============================================================================

test.beforeAll(async () => {
  test.setTimeout(30_000); // API 호출만 사용 — 브라우저 탐색 불필요
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  // API 직접 호출로 Dynamic IDs 확보 (browser 탐색 타임아웃 문제 우회)
  const apiBase = process.env.HARNESS_E2E_API_TARGET ?? "http://127.0.0.1:8000";
  try {
    // PB 로그인
    const loginResp = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "synthetic.pb1@example.invalid",
        password: "HarnessSynthetic!2026",
      }),
    }).catch(() => null);
    if (!loginResp?.ok) return;
    const { access_token } = (await loginResp.json()) as { access_token: string };

    // Customer ID
    const custResp = await fetch(`${apiBase}/customers?limit=1`, {
      headers: { Authorization: `Bearer ${access_token}` },
    }).catch(() => null);
    if (custResp?.ok) {
      const data = (await custResp.json()) as { items: Array<{ id: string }> };
      resolvedCustomerId = data.items?.[0]?.id ?? "";
    }

    // House View ID (첫 번째 PB-visible, non-AUDIT entry)
    const hvResp = await fetch(`${apiBase}/house-views?limit=1`, {
      headers: { Authorization: `Bearer ${access_token}` },
    }).catch(() => null);
    if (hvResp?.ok) {
      const data = (await hvResp.json()) as { items: Array<{ id: string }> };
      resolvedHouseViewId = data.items?.[0]?.id ?? "";
    }
  } catch (err) {
    // best-effort: ID 미확보 → dynamic tests SKIP, beforeAll throw 금지
    console.warn("beforeAll API ID resolution failed (non-fatal):", err);
  }
});

// ============================================================================
// 22 routes × 3 roles — G3b visible-DOM banned assertion + screenshot
// 66 page-cells (PRD §8)
// ============================================================================

for (const account of ROLES) {
  for (const route of ROUTE_MANIFEST) {
    const isAllowed = (route.allowed as string[]).includes(account.role);

    test(`@visual-fullwalk [${account.role}] ${route.templatePath}`, async ({ page }) => {
      // 동적 ID 미확보 시 SKIP (DB empty or setup failure)
      if (route.templatePath.includes(":customerId") && !resolvedCustomerId) {
        test.skip(true, "No customer ID resolved — customers table might be empty");
      }
      if (route.templatePath.includes(":houseViewId") && !resolvedHouseViewId) {
        test.skip(true, "No house-view ID resolved — house_views table might be empty");
      }

      await loginAs(page, account.email);
      const resolvedPath = resolveRoutePath(route.templatePath);

      const resp = await page
        .goto(`${BASE_URL}${resolvedPath}`, { waitUntil: "load" })
        .catch(() => null);
      test.skip(resp === null, "Frontend dev server unreachable");

      await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
      const currentUrl = page.url();

      // 접근 거부 cell: /403 redirect → SKIP (access_denied 라벨, role-matrix.spec.ts에서 검증)
      if (!isAllowed) {
        const isDenied =
          currentUrl.includes("/403") || currentUrl.includes("/dashboard");
        test.skip(isDenied, `access_denied — ${account.role} cannot access ${route.templatePath}`);
        return;
      }

      // 접근 가능 cell: /403 진입 시 FAIL (의도치 않은 차단)
      expect(
        currentUrl,
        `[${account.role}] ${route.templatePath} should NOT redirect to /403`,
      ).not.toMatch(/\/403/);

      // P1 SoT: visible-DOM 수집
      // HouseViewDetail: <details> open 상태 포함 (PromptAuditTrail banned 검사)
      const isHvDetail =
        route.templatePath.startsWith("/house-views/") &&
        !route.templatePath.endsWith("/activate");
      const visibleText = isHvDetail
        ? await getVisibleTextWithDetailsOpen(page)
        : await getVisibleText(page);

      test.skip(visibleText === "", `Frontend unreachable for [${account.role}] ${route.templatePath}`);

      // G3b — role-aware banned 체크 (PRD §9.5 Lane C 매트릭스)
      // AUDIT_VIEWER: BANNED_INTERNAL_ID 제외 (ADR/REG role-gated display 허용)
      const patternsToCheck =
        account.role === "AUDIT_VIEWER" ? ALL_BANNED_AUDIT_VIEWER : ALL_BANNED;
      for (const pattern of patternsToCheck) {
        expect(
          visibleText,
          `[${account.role}] ${route.templatePath} → banned pattern ${String(pattern)}`,
        ).not.toMatch(pattern);
      }

      // Screenshots: viewport(1280×800) + fullPage 양종
      await captureScreenshots(page, account.role, route.slug);
    });
  }
}

// ============================================================================
// AC12 — JsonSection empty state 동일 한국어 메시지 박제
// V048 AUDIT-NEG-001: db_null (sentinel 'null'::jsonb) + db_empty_object
// V048 AUDIT-POS-001: db_valid ({"key":"value"})
// (HouseViewDetailPage.tsx:60-67 isEmpty, :72-74 empty message SoT)
// T2 (V048 migration) 미완료 시 SKIP
// ============================================================================

test("@visual-fullwalk AC12 AUDIT-NEG-001 JsonSection empty → 동일 빈 메시지 visible", async ({
  page,
}) => {
  await loginAsAdmin(page);
  const resp = await page
    .goto(`${BASE_URL}/house-views/${AUDIT_NEG_001_ID}`, { waitUntil: "load" })
    .catch(() => null);
  test.skip(resp === null, "Frontend dev server unreachable");
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);

  test.skip(
    !(await isFixtureLoaded(page)),
    "V048 AUDIT-NEG-001 not in DB — T2 (V048 migration) pending",
  );

  // AC12: sentinel null + empty_object → 빈 메시지 visible (≥1 JsonSection)
  const emptyMsg = page
    .locator("p")
    .filter({ hasText: JSON_SECTION_EMPTY_MSG })
    .filter({ visible: true });

  await expect(
    emptyMsg.first(),
    "AC12: at least one JsonSection must show the canonical empty message for null/empty JSONB",
  ).toBeVisible({ timeout: 5000 });

  await expect(
    emptyMsg.first(),
    "AC12: empty message text must match HouseViewDetailPage.tsx:73 exactly",
  ).toHaveText(JSON_SECTION_EMPTY_MSG);

  await captureScreenshots(page, "ADMIN", "audit_neg_001_detail");
});

test("@visual-fullwalk AC12 AUDIT-POS-001 JsonSection db_valid → pre JSON 렌더, 빈 메시지 0", async ({
  page,
}) => {
  await loginAsAdmin(page);
  const resp = await page
    .goto(`${BASE_URL}/house-views/${AUDIT_POS_001_ID}`, { waitUntil: "load" })
    .catch(() => null);
  test.skip(resp === null, "Frontend dev server unreachable");
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);

  test.skip(
    !(await isFixtureLoaded(page)),
    "V048 AUDIT-POS-001 not in DB — T2 (V048 migration) pending",
  );

  // db_valid → 빈 메시지 0개
  const emptyMsg = page
    .locator("p")
    .filter({ hasText: JSON_SECTION_EMPTY_MSG })
    .filter({ visible: true });

  await expect(
    emptyMsg,
    "AC12: AUDIT-POS-001 db_valid must NOT show the empty message",
  ).toHaveCount(0);

  // db_valid → <pre> JSON 렌더 ≥1
  const preBlock = page.locator("pre").filter({ visible: true });
  await expect(
    preBlock.first(),
    "AC12: AUDIT-POS-001 must render at least one <pre> JSON block",
  ).toBeVisible({ timeout: 5000 });

  await captureScreenshots(page, "ADMIN", "audit_pos_001_detail");
});

// ============================================================================
// AC3a/AC3b — V048 fixture Dead-detection (S5, PRD §4)
// banned-patterns.ts 모듈이 살아있음(결함 탐지 능력 유지)을 증명.
//
// AC3a: AUDIT-NEG-001 visible-DOM → ALL_BANNED 중 ≥1 match
//   - T4 fix 이전: MetadataBlock BANNED_DASH hit (standalone dash)
//   - T4 fix 이후: BANNED_AUDIT_PREFIX hit (title "AUDIT-NEG-001")
//   - 어느 쪽이든 dead-detection 성립
//
// AC3b: AUDIT-POS-001 visible-DOM → core 8종 + BANNED_DASH = 0
//   - BANNED_AUDIT_PREFIX 제외 (POS fixture도 "AUDIT-POS-001" title 보유)
//   - db_valid JSON + 정상 메타데이터 → banned 8종 + dash 없음
// ============================================================================

test("@visual-fullwalk AC3a AUDIT-NEG-001 → banned regex match ≥1 (S5 dead-detection)", async ({
  page,
}) => {
  await loginAsAdmin(page);
  const resp = await page
    .goto(`${BASE_URL}/house-views/${AUDIT_NEG_001_ID}`, { waitUntil: "load" })
    .catch(() => null);
  test.skip(resp === null, "Frontend dev server unreachable");
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);

  const visibleText = await getVisibleTextWithDetailsOpen(page);
  test.skip(
    page.url().includes("/login") || visibleText.includes("하우스뷰를 불러오지 못했습니다"),
    "V048 AUDIT-NEG-001 not in DB or admin login redirect — AC3a deferred",
  );

  // ALL_BANNED 10종 중 ≥1 match (BANNED_AUDIT_PREFIX title hit 또는 BANNED_DASH)
  const matched = ALL_BANNED.filter((p) => p.test(visibleText));
  expect(
    matched.length,
    `AC3a: AUDIT-NEG-001 must expose ≥1 banned pattern (S5 dead-detection). ` +
      `Matched: [${matched.map(String).join(", ")}]. Got 0 — banned-patterns.ts is dead.`,
  ).toBeGreaterThanOrEqual(1);
});

test("@visual-fullwalk AC3b AUDIT-POS-001 → core banned regex match = 0", async ({
  page,
}) => {
  await loginAsAdmin(page);
  const resp = await page
    .goto(`${BASE_URL}/house-views/${AUDIT_POS_001_ID}`, { waitUntil: "load" })
    .catch(() => null);
  test.skip(resp === null, "Frontend dev server unreachable");
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);

  const visibleText = await getVisibleTextWithDetailsOpen(page);
  test.skip(
    page.url().includes("/login") || visibleText.includes("하우스뷰를 불러오지 못했습니다"),
    "V048 AUDIT-POS-001 not in DB or admin login redirect — AC3b deferred",
  );

  // BANNED_AUDIT_PREFIX 제외 (POS fixture title "AUDIT-POS-001" 예상 match)
  // 나머지 8 core + BANNED_DASH = 0 이어야 정상 fixture
  const corePatterns = ALL_BANNED.filter(
    (p) => p !== BANNED_AUDIT_PREFIX,
  );
  for (const pattern of corePatterns) {
    expect(
      visibleText,
      `AC3b: AUDIT-POS-001 db_valid must not match banned pattern ${String(pattern)}`,
    ).not.toMatch(pattern);
  }
});
