import { expect, test } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";

const PASSWORD = "HarnessSynthetic!2026";

const ROLES: Array<{ name: string; email: string; routes: string[] }> = [
  {
    name: "WM",
    email: "synthetic.wm1@example.invalid",
    routes: ["/dashboard", "/customers", "/house-views", "/nba", "/aftercare", "/email-drafts"],
  },
  {
    name: "BRANCH_MANAGER",
    email: "synthetic.branch.manager@example.invalid",
    routes: ["/dashboard", "/customers", "/house-views", "/nba", "/aftercare"],
  },
  {
    name: "AUDIT_VIEWER",
    email: "synthetic.audit@example.invalid",
    routes: ["/audit", "/audit-viewer", "/quarantine", "/ai-admin-dashboard"],
  },
];

const BANNED_PG_MICRO = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+/;
const BANNED_SHORT_TZ = /\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?[+-]\d{2}(?!:)/;
const BANNED_ISO_MICRO = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+/;
const BANNED_RAW_DB_FIELD = /\b(source_as_of|created_at|generated_at|observed_at)\b/;
const BANNED_PLACEHOLDER =
  /응답을 기다리는 중|정보를 불러오는 중|최신 생성 정보 준비 중|생성 대기|모델 대기/;
const BANNED_ENGLISH_FRAGMENTS = [
  "Failing row contains",
  "Official KRX returned no",
  "PYKRX returned no persisted",
  "KRX collector is disabled",
  "evidence",
  "persisted",
  "snapshot",
  "denominator",
];

async function loginAs(page: import("@playwright/test").Page, email: string): Promise<void> {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
  await page.locator("input[type=email]").fill(email);
  await page.locator("input[type=password]").fill(PASSWORD);
  await page.locator("button[type=submit]").click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 8000 });
}

for (const role of ROLES) {
  for (const route of role.routes) {
    test(`@qa-multi-role ${role.name} ${route} → clean banker UI`, async ({ page }) => {
      await loginAs(page, role.email);
      await page.goto(`${BASE_URL}${route}`, { waitUntil: "load" });
      await page.waitForLoadState("networkidle");
      const text = (await page.textContent("body")) ?? "";

      const failures: string[] = [];
      if (BANNED_PG_MICRO.test(text)) failures.push(`PG μs ts leaked`);
      if (BANNED_SHORT_TZ.test(text)) failures.push(`+NN short TZ leaked`);
      if (BANNED_ISO_MICRO.test(text)) failures.push(`ISO μs ts leaked`);
      if (BANNED_RAW_DB_FIELD.test(text)) {
        failures.push(`raw DB column leaked: ${text.match(BANNED_RAW_DB_FIELD)?.[0]}`);
      }
      if (BANNED_PLACEHOLDER.test(text)) {
        failures.push(`placeholder visible: ${text.match(BANNED_PLACEHOLDER)?.[0]}`);
      }
      for (const eng of BANNED_ENGLISH_FRAGMENTS) {
        if (text.includes(eng)) failures.push(`English fragment: ${eng}`);
      }

      console.log(`  [${role.name} ${route}] ${failures.length === 0 ? "✓ clean" : "✗ " + failures.join(" | ")}`);
      expect(failures, failures.join(" | ")).toEqual([]);
    });
  }
}
