import { defineConfig, devices } from "@playwright/test";

/**
 * WMAH Audit — Stage 2 Lane 1 Playwright config.
 *
 * - testDir: this directory (tests/audit-e2e)
 * - outputDir: audit-out/behavior (per-test artifacts)
 * - reporters: html / junit / blob under audit-out/behavior
 * - chromium-only project; firefox/webkit are handled in separate lanes.
 */
export default defineConfig({
  testDir: "./",
  // Per-test artifact dir. Kept as a subfolder of audit-out/behavior so the
  // HTML reporter (sibling) does not clash with the test results scan path
  // (Playwright forbids outputDir to enclose the html-report folder).
  outputDir: "../../audit-out/behavior/test-results",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  retries: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "../../audit-out/behavior/html-report", open: "never" }],
    ["junit", { outputFile: "../../audit-out/behavior/junit.xml" }],
    ["blob", { outputFile: "../../audit-out/behavior/blob-report.zip" }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? `http://127.0.0.1:${process.env.HARNESS_WEB_PORT ?? "8000"}`,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
