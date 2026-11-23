/**
 * qa-audit-quality.spec.ts — Stage 8 screen-quality verification (DEV-10).
 *
 * For each PB-visible page rendered as the synthetic PB user, assert:
 *   1. No English banned words (evidence, persisted, snapshot, universe,
 *      denominator, staff display).
 *   2. No internal taxonomy identifier leakage (ADR-###, W#-T#, REG-0#).
 *   3. No test fixture markers (GOLDEN_TEST, RALPH-QA, Synthetic boundary).
 *   4. No ISO microsecond timestamps (e.g. 2026-04-20T13:52:53.650391Z).
 *
 * Re-uses the qa-audit Playwright login flow but adds focused regex
 * assertions for screen quality. Skips routes the PB role cannot access
 * (the route's RBAC layer returns 403 → /dashboard fallback content).
 *
 * ─── P1 Visible-DOM 전환 (Visual Full-Walk Audit v7.1) ───────────────────────
 * G3a/G3b 분리: screenshot 존재(G3a) + banned 0(G3b) 별도 assertion.
 * banned-patterns.ts single-module import (S5 단일 모듈 SoT).
 * page.textContent("body") → getVisibleText() 전환 (P1 SoT).
 * ─────────────────────────────────────────────────────────────────────────────
 */
import { expect, test, type Page } from "@playwright/test";
import {
  BANNED_ENGLISH,
  BANNED_INTERNAL_ID,
  BANNED_TEST_FIXTURE,
  BANNED_ISO_MICRO,
  BANNED_PG_MICRO_TIMESTAMP,
  BANNED_PG_SHORT_TZ,
  BANNED_PLACEHOLDER,
  BANNED_RAW_DB_FIELD,
} from "./_shared/banned-patterns";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";

const PB_VISIBLE_PAGES = [
  "/dashboard",
  "/customers",
  "/consultations/SYN-CUST-001",
  "/nba",
  "/aftercare",
  "/email-drafts",
  "/house-views",
  "/rag",
  "/dispute-cases",
  "/rights-notice",
  "/ai-model-cards",
  "/ai-policy",
  "/korean-ai-act",
];

// Banned patterns are imported from ./_shared/banned-patterns (S5 단일 모듈 SoT)
const REQUIRED_WATERMARK = /합성 데이터/;
// At least one Asia/Seoul banker timestamp YYYY-MM-DD HH:MM (no seconds) so
// pages that should show provenance prove they actually formatted something.
const REQUIRED_BANKER_TIMESTAMP = /\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?!:)/;
// Pages where formatted provenance must be visible for the route to be useful.
const PAGES_REQUIRING_BANKER_TIMESTAMP = new Set<string>(["/dashboard"]);

/**
 * P1 SoT: visible-DOM text extractor (Visual Full-Walk Audit v7.1)
 * TreeWalker로 visibility:hidden / display:none / aria-hidden=true 제외 노드만 수집.
 * page.textContent("body") 사용 금지.
 */
async function getVisibleText(page: Page): Promise<string> {
  return page.evaluate((): string => {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node: Node): number {
          const el = node.parentElement;
          if (!el) return NodeFilter.FILTER_REJECT;
          if (el.closest("[aria-hidden='true']")) return NodeFilter.FILTER_REJECT;
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

async function loginAsPB(page: Page): Promise<void> {
  // Up to 3 attempts; transient login bounces have been observed under heavy
  // Playwright parallel load (rate limiter back-off, redis fail-open windows).
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
    const emailInput = page.locator('input[type=email], input[name=email]').first();
    if ((await emailInput.count().catch(() => 0)) === 0) {
      // Already authenticated — landed somewhere other than login.
      return;
    }
    await emailInput.fill("synthetic.pb2@example.invalid");
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

async function gotoAuthenticated(page: Page, route: string): Promise<string> {
  await loginAsPB(page);
  let resp = await page.goto(`${BASE_URL}${route}`, { waitUntil: "load" }).catch(() => null);
  if (resp === null) {
    return "";
  }
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
  // P1 SoT: visible-DOM (page.textContent("body") 금지)
  let text = await getVisibleText(page);
  // If we bounced back to the login form, retry the login + navigation once.
  if (/직원 로그인/.test(text) && /이메일|비밀번호/.test(text)) {
    await loginAsPB(page);
    resp = await page.goto(`${BASE_URL}${route}`, { waitUntil: "load" }).catch(() => null);
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => null);
    text = await getVisibleText(page);
  }
  return text;
}

for (const route of PB_VISIBLE_PAGES) {
  test(`@qa-quality PB role ${route} → no banned tokens`, async ({ page }) => {
    const text = await gotoAuthenticated(page, route);
    test.skip(text === "", "Frontend dev server unreachable");

    expect(text, `[${route}] English banned word leak`).not.toMatch(BANNED_ENGLISH);
    expect(text, `[${route}] internal identifier leak`).not.toMatch(BANNED_INTERNAL_ID);
    expect(text, `[${route}] test fixture leak`).not.toMatch(BANNED_TEST_FIXTURE);
    expect(text, `[${route}] ISO microsecond timestamp leak`).not.toMatch(BANNED_ISO_MICRO);
    expect(text, `[${route}] PostgreSQL microsecond timestamp leak`).not.toMatch(BANNED_PG_MICRO_TIMESTAMP);
    expect(text, `[${route}] PostgreSQL short timezone leak`).not.toMatch(BANNED_PG_SHORT_TZ);
    expect(text, `[${route}] loading/placeholder copy still visible after load`).not.toMatch(BANNED_PLACEHOLDER);
    expect(text, `[${route}] raw DB column name leaked into prose`).not.toMatch(BANNED_RAW_DB_FIELD);
    expect(text, `[${route}] synthetic watermark missing`).toMatch(REQUIRED_WATERMARK);

    if (PAGES_REQUIRING_BANKER_TIMESTAMP.has(route)) {
      expect(text, `[${route}] no Asia/Seoul YYYY-MM-DD HH:MM timestamp shown`).toMatch(
        REQUIRED_BANKER_TIMESTAMP,
      );
    }
  });
}

test("@qa-quality dashboard surfaces a real house view summary", async ({ page }) => {
  const text = await gotoAuthenticated(page, "/dashboard");
  test.skip(text === "", "Frontend dev server unreachable");

  // House view summary must contain a non-trivial Korean sentence — empty
  // strings or "—" alone would slip through the banned-token gate but still
  // leave the PB user looking at an unusable card.
  expect(text, "house view summary card looks empty or placeholder").toMatch(
    /최신 하우스뷰 요약[\s\S]{0,80}[가-힣][\s\S]{20,}/,
  );
  // Top200 KRX coverage card is intentionally suppressed on the PB dashboard
  // when the gate does not apply to the profile — block the "차단" panel
  // from being mistakenly re-introduced for that case.
  expect(text, "Top200 차단 panel re-introduced despite gate-not-required profile").not.toMatch(
    /상위 200개 공식 KRX 커버리지[\s\S]{0,200}차단/,
  );
});

test("@qa-quality Rights Notice button copy", async ({ page }) => {
  const text = await gotoAuthenticated(page, "/rights-notice");
  expect(text).toContain("다음에 확인");
  expect(text).not.toContain("취소 (나중에 확인)");
});

test("@qa-quality Consultation page anchors to synthetic customer", async ({ page }) => {
  const text = await gotoAuthenticated(page, "/consultations/SYN-CUST-001");
  expect(text).not.toContain("상단 고객 목록에서 고객을 선택하세요");
});
