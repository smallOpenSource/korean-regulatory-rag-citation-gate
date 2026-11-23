/**
 * Wave-Audit-Defect-Fix C4 — MarketingReviewPage 신규 page structural test.
 *
 * Plan §6 line 369: 1 POST endpoint (marketing_review_submitted canonical
 * pre-existing in core/audit.py:94-97; no new migration). Page enables the
 * 광고심의 게이트 — single-shot submit returns PASS/BLOCK + issue codes.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SRC = fs.readFileSync(
  path.resolve(__dirname, "../pages/MarketingReviewPage.tsx"),
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

describe("C4: MarketingReviewPage structural contract", () => {
  it("file exists at canonical location", () => {
    expect(SRC.length).toBeGreaterThan(100);
  });

  it("exports MarketingReviewPage component", () => {
    expect(SRC).toMatch(/export function MarketingReviewPage\b/);
  });

  it("binds POST /marketing-review with request body fields", () => {
    expect(SRC).toContain('postResource<MarketingReviewResponse>("/marketing-review"');
    for (const field of [
      "subject",
      "body",
      "marketing_classified",
      "pre_review_number",
      "consultation_id",
    ]) {
      expect(SRC).toContain(field);
    }
  });

  it("decodes both PASS and BLOCK decisions explicitly", () => {
    expect(SRC).toContain("MARKETING_REVIEW_PASS");
    expect(SRC).toContain("MARKETING_REVIEW_BLOCK");
  });

  it("gates submit form on canSubmit (WRITE_ROLES = PB/WM/ADMIN)", () => {
    expect(SRC).toContain("useAuthStore");
    expect(SRC).toContain('WRITE_ROLES = new Set(["PB", "WM", "ADMIN"])');
    expect(SRC).toContain("canSubmit");
  });

  it("renders issue_codes when BLOCK decision lands", () => {
    expect(SRC).toContain("issue_codes");
  });

  it("redacted AI reasoning passed through (server-side hash, not raw model output)", () => {
    expect(SRC).toContain("ai_reasoning");
  });
});

describe("C4: route + access registration", () => {
  it("App.tsx registers /marketing-review under ProtectedRoute", () => {
    expect(APP).toContain('"/marketing-review"');
    expect(APP).toContain('routeKey="marketingReview"');
    expect(APP).toContain("MarketingReviewPage");
  });

  it("access.ts grants PB/WM/BRANCH_MANAGER/ADMIN/AUDIT_VIEWER (read)", () => {
    expect(ACCESS).toMatch(
      /marketingReview:\s*\["PB",\s*"WM",\s*"BRANCH_MANAGER",\s*"ADMIN",\s*"AUDIT_VIEWER"\]/,
    );
  });

  it("types.ts RouteKey includes marketingReview", () => {
    expect(TYPES).toContain('"marketingReview"');
  });
});
