/**
 * Wave-Audit-Defect-Fix C1 — ConsentsPage 신규 page structural test.
 *
 * Plan §6 line 366 acceptance: PB role click-through 4 form submit + audit
 * row 5건. Page binds 5 backend endpoints and uses backend's existing
 * canonical action codes (consent_recorded / consent_withdrawn /
 * marketing_consent_withdrawn / general_bundle_consent — all in
 * core/audit.py:64-71). No new migration.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SRC = fs.readFileSync(
  path.resolve(__dirname, "../pages/ConsentsPage.tsx"),
  "utf-8",
);
const APP = fs.readFileSync(
  path.resolve(__dirname, "../App.tsx"),
  "utf-8",
);
const ACCESS = fs.readFileSync(
  path.resolve(__dirname, "../lib/access.ts"),
  "utf-8",
);
const TYPES = fs.readFileSync(
  path.resolve(__dirname, "../lib/types.ts"),
  "utf-8",
);

describe("C1: ConsentsPage structural contract", () => {
  it("file exists at canonical location", () => {
    expect(SRC.length).toBeGreaterThan(100);
  });

  it("exports ConsentsPage component", () => {
    expect(SRC).toMatch(/export function ConsentsPage\b/);
  });

  it("binds 5 backend endpoints (customer view + 4 mutations)", () => {
    expect(SRC).toContain("/consents/customer/");
    expect(SRC).toContain('"/consents/grant"');
    expect(SRC).toContain('"/consents/withdraw"');
    expect(SRC).toContain('"/consents/marketing/stop"');
    expect(SRC).toContain('"/consents/general-bundle"');
  });

  it("exposes 4 backend-validated consent types", () => {
    for (const t of [
      "GENERAL_BUNDLE",
      "INFORMATION_USE",
      "MARKETING_CONTACT",
      "DATA_SHARING_THIRD_PARTY",
    ]) {
      expect(SRC).toContain(t);
    }
  });

  it("gates form actions on canSubmit (WRITE_ROLES = PB/WM)", () => {
    expect(SRC).toContain("useAuthStore");
    expect(SRC).toMatch(/WRITE_ROLES\s*=\s*new Set\(\["PB",\s*"WM"\]\)/);
    expect(SRC).toContain("canSubmit");
  });

  it("renders the four submit buttons (grant / withdraw / bundle / marketing-stop)", () => {
    expect(SRC).toContain("동의 등록");
    expect(SRC).toContain("동의 철회");
    expect(SRC).toContain("일괄동의 발급");
    expect(SRC).toContain("마케팅 수신 중단");
  });

  it("customer view query is enabled only when customerId is set", () => {
    expect(SRC).toContain("enabled: customerId.trim().length > 0");
  });
});

describe("C1: route + access registration", () => {
  it("App.tsx registers /consents under ProtectedRoute", () => {
    expect(APP).toContain('"/consents"');
    expect(APP).toContain('routeKey="consents"');
    expect(APP).toContain("ConsentsPage");
  });

  it("access.ts grants every staff role read; PB/WM write gated in page", () => {
    expect(ACCESS).toMatch(
      /consents:\s*\["PB",\s*"WM",\s*"BRANCH_MANAGER",\s*"ADMIN",\s*"AUDIT_VIEWER"\]/,
    );
  });

  it("types.ts RouteKey includes consents", () => {
    expect(TYPES).toContain('"consents"');
  });
});
