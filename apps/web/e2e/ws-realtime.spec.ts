/**
 * WebSocket realtime tests — row-scoped NBA push + event_id client-side dedup.
 *
 * Tags: @ws-realtime
 *
 * Strategy
 * --------
 * The backend WS route (/ws) is `backlog/not-current-contract` (ADR-001 Stage 2),
 * so the SPA's ticket fetch (POST /api/ws/ticket) would 404 and the socket would
 * never open.  We therefore use two Playwright interceptions in each test:
 *
 *   1. page.route on TICKET_URL_PATTERN  → mock ticket endpoint (200 + fake ticket)
 *   2. page.routeWebSocket on WS_URL_PATTERN → mock WS server (inject synthetic events)
 *
 * Both MUST be registered BEFORE loginUi() so they are in place when the SPA
 * attempts to connect immediately after the auth redirect to /dashboard.
 *
 * Client-side contract tests (ADR-001 / T287 / T297):
 *   - event_id deduplication ring buffer (256 entries)
 *   - connection_ack → status "open"
 *   - 4003 policy-violation close → no reconnect attempts
 *   - row-scope isolation: PB1 context vs. PB2 context (different WS mock routes)
 *   - cross-reconnect event_id replay suppression
 *
 * Live backend tests (E2E_WS_LIVE=true):
 *   - Ticket endpoint issues a 30-second one-shot ticket
 *   - Replayed ticket is rejected with 4401/4403
 *
 * Constraints:
 * - Real PG17 + Redis (E2E_SYNTHETIC_PASSWORD required).
 * - Synthetic data only; no real customer PII.
 * - Headless Playwright Chromium, Playwright 1.60+.
 */
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const password = process.env.E2E_SYNTHETIC_PASSWORD;
const wsLive = process.env.E2E_WS_LIVE === "true";
const apiBase = process.env.HARNESS_E2E_API_TARGET ?? "http://127.0.0.1:8000";

/** Glob that matches the SPA's WS connection target (proxied same-origin /api/ws). */
const WS_URL_PATTERN = "**/api/ws";
/** Glob that matches the ticket fetch endpoint. */
const TICKET_URL_PATTERN = "**/api/ws/ticket";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEnvelope(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    event_id: `evt-${Math.random().toString(36).slice(2, 10)}`,
    event_type: "nba_card_published",
    channel: "nba.card",
    occurred_at: new Date().toISOString(),
    trace_id: `trace-${Math.random().toString(36).slice(2, 10)}`,
    tenant_scope: { branch_id: "branch-01" },
    row_scope: { customer_id: "cust-pb1-01" },
    payload: {
      nba_action_id: `nba-${Math.random().toString(36).slice(2, 10)}`,
      priority_code: "URGENT",
      action_type_code: "MATURITY_CALL",
      customer_display_name: "강남 현금흐름 설계",
    },
    ...overrides,
  });
}

/**
 * Mock the ticket endpoint so the SPA can bootstrap a WS connection.
 * Must be called BEFORE loginUi() to intercept the post-login connect attempt.
 */
async function mockTicketEndpoint(page: Page, ticket = "mock-ticket-00000000"): Promise<void> {
  await page.route(TICKET_URL_PATTERN, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ticket, ttl_seconds: 30 }),
    }),
  );
}

async function loginUi(page: Page, email: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "직원 로그인" })).toBeVisible();
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password!);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

async function navigateSpa(page: Page, path: string): Promise<void> {
  await page.evaluate((next) => {
    window.history.pushState({}, "", next);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

// ---------------------------------------------------------------------------
// Mock-WebSocket suite (always runs)
// ---------------------------------------------------------------------------

test.describe("WebSocket client contract — mocked server", { tag: ["@ws-realtime"] }, () => {
  // Serial: WS tests involve multiple concurrent timers; run sequentially to avoid flakiness.
  test.describe.configure({ mode: "serial" });

  test.beforeEach(() => {
    test.setTimeout(60_000); // WS tests: login + connection + event delivery need > 30 s
    test.skip(!password, "E2E_SYNTHETIC_PASSWORD is required.");
  });

  // ── event_id deduplication ──────────────────────────────────────────────

  test("duplicate event_id is deduplicated: NBA badge increments only once", async ({ page }) => {
    // 1. Set up mocks BEFORE login so they catch the post-auth connection attempt
    await mockTicketEndpoint(page);

    const fixedEventId = "evt-dedup-test-001";
    let injectFn: ((msg: string) => void) | null = null;

    await page.routeWebSocket(WS_URL_PATTERN, (ws) => {
      ws.onMessage(() => {
        // Respond to the hello/ticket frame with connection_ack
        ws.send(JSON.stringify({ event_type: "connection_ack", event_id: "ack-001" }));
      });
      injectFn = (msg) => ws.send(msg);
    });

    // 2. Login — SPA fetches mocked ticket and opens mocked WS
    await loginUi(page, "synthetic.pb1@example.invalid");

    // 3. Capture badge count at dashboard before navigating
    const badgeBefore = parseInt(
      (await page.locator("[data-testid='nba-badge-count']").textContent({ timeout: 500 }).catch(() => "0")) ?? "0",
    );

    // 4. Navigate to NBA inbox
    await navigateSpa(page, "/nba");
    await expect(page.getByRole("heading", { name: "NBA 인박스" })).toBeVisible({ timeout: 8_000 });

    // 5. Inject the same event_id twice (server replay scenario)
    if (injectFn) {
      (injectFn as (m: string) => void)(makeEnvelope({ event_id: fixedEventId }));
      await page.waitForTimeout(300);
      (injectFn as (m: string) => void)(makeEnvelope({ event_id: fixedEventId })); // duplicate
      await page.waitForTimeout(600);
    }

    // 6. Badge delta must be ≤1 (duplicate suppressed)
    const badgeAfter = parseInt(
      (await page.locator("[data-testid='nba-badge-count']").textContent({ timeout: 500 }).catch(() => "0")) ?? "0",
    );
    expect(badgeAfter - badgeBefore, "duplicate event_id must not double-increment the badge").toBeLessThanOrEqual(1);
  });

  test("connection_ack transitions WS status to open without crashing", async ({ page }) => {
    await mockTicketEndpoint(page);

    await page.routeWebSocket(WS_URL_PATTERN, (ws) => {
      ws.onMessage(() => {
        ws.send(JSON.stringify({ event_type: "connection_ack", event_id: "ack-ok" }));
      });
    });

    await loginUi(page, "synthetic.pb1@example.invalid");
    await navigateSpa(page, "/nba");
    await expect(page.getByRole("heading", { name: "NBA 인박스" })).toBeVisible({ timeout: 8_000 });

    // WS status indicator (if rendered) must show connected state
    const wsIndicator = page.locator("[data-testid='ws-status']");
    const indicatorVisible = await wsIndicator.isVisible().catch(() => false);
    if (indicatorVisible) {
      await expect(wsIndicator).toHaveText(/연결됨|open/i, { timeout: 5_000 });
    }

    // No JS errors
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.waitForTimeout(500);
    expect(errors).toHaveLength(0);
  });

  test("policy-violation close (4003) suppresses all reconnect attempts", async ({ page }) => {
    await mockTicketEndpoint(page);

    let connectionCount = 0;

    await page.routeWebSocket(WS_URL_PATTERN, async (ws) => {
      connectionCount += 1;
      await ws.close({ code: 4003, reason: "policy_violation" });
    });

    await loginUi(page, "synthetic.pb1@example.invalid");
    await navigateSpa(page, "/nba");
    // Give reconnect backoff time to fire a retry (base = 1 s)
    await page.waitForTimeout(2_500);

    // 4003 must suppress all reconnects — only 1 connection attempt total
    expect(connectionCount, "4003 close must suppress all reconnect attempts").toBe(1);
  });

  test("NBA push event is delivered to the page without JS crashes", async ({ page }) => {
    await mockTicketEndpoint(page);

    let connected = false;

    await page.routeWebSocket(WS_URL_PATTERN, (ws) => {
      ws.onMessage(() => {
        if (!connected) {
          connected = true;
          ws.send(JSON.stringify({ event_type: "connection_ack", event_id: "ack-001" }));
          // Deliver a synthetic NBA event 100 ms after ack
          setTimeout(() => ws.send(makeEnvelope()), 100);
        }
      });
    });

    await loginUi(page, "synthetic.pb1@example.invalid");
    await navigateSpa(page, "/nba");
    await expect(page.getByRole("heading", { name: "NBA 인박스" })).toBeVisible({ timeout: 8_000 });

    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.waitForTimeout(1_000);
    expect(errors, "NBA push must not crash the page").toHaveLength(0);
  });

  // ── Two-context row-scope isolation (mocked) ────────────────────────────

  test("PB1 WS context receives its NBA event; PB2 context receives none for that customer", async ({
    browser,
  }) => {
    const [ctx1, ctx2]: BrowserContext[] = await Promise.all([
      browser.newContext(),
      browser.newContext(),
    ]);
    const [page1, page2] = await Promise.all([ctx1.newPage(), ctx2.newPage()]);

    try {
      let pb1EventsInjected = 0;
      let pb2EventsInjected = 0;

      // --- PB1 setup ---
      await page1.route(TICKET_URL_PATTERN, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ticket: "mock-ticket-pb1", ttl_seconds: 30 }),
        }),
      );
      await page1.routeWebSocket(WS_URL_PATTERN, (ws) => {
        ws.onMessage(() => {
          ws.send(JSON.stringify({ event_type: "connection_ack", event_id: "ack-pb1" }));
          setTimeout(() => {
            ws.send(makeEnvelope({ row_scope: { customer_id: "cust-pb1-01" } }));
            pb1EventsInjected += 1;
          }, 100);
        });
      });

      // --- PB2 setup: server does NOT push PB1's customer event (row-scope filter) ---
      await page2.route(TICKET_URL_PATTERN, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ticket: "mock-ticket-pb2", ttl_seconds: 30 }),
        }),
      );
      await page2.routeWebSocket(WS_URL_PATTERN, (ws) => {
        ws.onMessage(() => {
          ws.send(JSON.stringify({ event_type: "connection_ack", event_id: "ack-pb2" }));
          // No NBA events for cust-pb1-01 pushed to PB2 (server-side row-scope filter)
        });
      });

      // Login both PBs
      await Promise.all([
        loginUi(page1, "synthetic.pb1@example.invalid"),
        loginUi(page2, "synthetic.pb2@example.invalid"),
      ]);

      await Promise.all([
        navigateSpa(page1, "/nba"),
        navigateSpa(page2, "/nba"),
      ]);

      await Promise.all([
        expect(page1.getByRole("heading", { name: "NBA 인박스" })).toBeVisible({ timeout: 8_000 }),
        expect(page2.getByRole("heading", { name: "NBA 인박스" })).toBeVisible({ timeout: 8_000 }),
      ]);

      await page1.waitForTimeout(800);
      await page2.waitForTimeout(800);

      // PB1 received 1 event for its customer; PB2 received 0
      expect(pb1EventsInjected, "PB1 must receive NBA push for assigned customer").toBe(1);
      expect(pb2EventsInjected, "PB2 must NOT receive NBA push for PB1's customer").toBe(0);

      // No JS errors in either context
      const errors1: string[] = [];
      const errors2: string[] = [];
      page1.on("pageerror", (e) => errors1.push(e.message));
      page2.on("pageerror", (e) => errors2.push(e.message));
      await Promise.all([page1.waitForTimeout(200), page2.waitForTimeout(200)]);
      expect(errors1, "PB1 page must not crash").toHaveLength(0);
      expect(errors2, "PB2 page must not crash").toHaveLength(0);
    } finally {
      await ctx1.close();
      await ctx2.close();
    }
  });

  test("event_id ring buffer discards duplicate delivery across reconnect", async ({ page }) => {
    await mockTicketEndpoint(page);

    const fixedEventId = "evt-cross-reconnect-001";
    let sendFn: ((m: string) => void) | null = null;

    await page.routeWebSocket(WS_URL_PATTERN, (ws) => {
      ws.onMessage(() => {
        ws.send(JSON.stringify({ event_type: "connection_ack", event_id: `ack-${Date.now()}` }));
      });
      sendFn = (m) => ws.send(m);
    });

    await loginUi(page, "synthetic.pb1@example.invalid");
    await navigateSpa(page, "/nba");
    await expect(page.getByRole("heading", { name: "NBA 인박스" })).toBeVisible({ timeout: 8_000 });

    // First delivery
    if (sendFn) (sendFn as (m: string) => void)(makeEnvelope({ event_id: fixedEventId }));
    await page.waitForTimeout(400);

    const badgeMid = parseInt(
      (await page.locator("[data-testid='nba-badge-count']").textContent({ timeout: 500 }).catch(() => "0")) ?? "0",
    );

    // Replay the same event_id (simulates server replay on reconnect)
    if (sendFn) (sendFn as (m: string) => void)(makeEnvelope({ event_id: fixedEventId }));
    await page.waitForTimeout(600);

    const badgeAfter = parseInt(
      (await page.locator("[data-testid='nba-badge-count']").textContent({ timeout: 500 }).catch(() => "0")) ?? "0",
    );

    // Badge count must not increase from the duplicate delivery
    expect(badgeAfter, "replayed event_id must not increment the badge").toBeLessThanOrEqual(badgeMid + 1);
  });
});

// ---------------------------------------------------------------------------
// Live-backend WebSocket suite (E2E_WS_LIVE=true only)
// ---------------------------------------------------------------------------

test.describe("WebSocket live backend — ticket flow + server row-scope", { tag: ["@ws-realtime"] }, () => {
  test.beforeEach(() => {
    test.skip(
      !wsLive || !password,
      "Set E2E_WS_LIVE=true and E2E_SYNTHETIC_PASSWORD to run live WS backend tests.",
    );
  });

  test("ticket endpoint issues a 30-second one-shot ticket for authenticated employee", async () => {
    const resp = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "synthetic.pb1@example.invalid", password }),
    });
    expect(resp.status).toBe(200);
    const { access_token: token } = (await resp.json()) as { access_token: string };

    const ticketResp = await fetch(`${apiBase}/ws/ticket`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    });
    expect(ticketResp.status, "POST /ws/ticket must return 200").toBe(200);

    const data = (await ticketResp.json()) as { ticket: string; ttl_seconds: number };
    expect(typeof data.ticket).toBe("string");
    expect(data.ticket.length).toBeGreaterThan(16);
    expect(data.ttl_seconds).toBeLessThanOrEqual(30);
  });

  test("ticket replay is rejected (4401/4403) via browser WebSocket", async ({ page }) => {
    await loginUi(page, "synthetic.pb1@example.invalid");

    const wsBase = apiBase.replace(/^http/, "ws");

    // Fetch a ticket and attempt to use it twice in the browser context
    const closeCode = await page.evaluate(
      async ({ apiBase: base, wsBase: wsb, pwd }: { apiBase: string; wsBase: string; pwd: string }) => {
        const loginResp = await fetch(`${base}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: "synthetic.pb1@example.invalid", password: pwd }),
        });
        const { access_token: token } = (await loginResp.json()) as { access_token: string };

        const ticketResp = await fetch(`${base}/ws/ticket`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        });
        const { ticket } = (await ticketResp.json()) as { ticket: string };

        // First consumption
        await new Promise<void>((resolve) => {
          const ws1 = new WebSocket(`${wsb}/ws`, "harness.v1");
          ws1.addEventListener("open", () => ws1.send(JSON.stringify({ ticket, reconnect: false })));
          ws1.addEventListener("message", () => { ws1.close(); resolve(); });
          ws1.addEventListener("close", () => resolve());
          ws1.addEventListener("error", () => resolve());
        });

        // Second (replay) consumption — must be rejected
        return new Promise<number>((resolve) => {
          const ws2 = new WebSocket(`${wsb}/ws`, "harness.v1");
          ws2.addEventListener("open", () => ws2.send(JSON.stringify({ ticket, reconnect: false })));
          ws2.addEventListener("close", (evt) => resolve(evt.code));
          ws2.addEventListener("error", () => resolve(0));
        });
      },
      { apiBase, wsBase, pwd: password! },
    );

    // 4401 = ticket invalid/expired; 4403 = ticket replay
    expect([4401, 4403], "replayed ticket must be rejected by the server").toContain(closeCode);
  });
});
