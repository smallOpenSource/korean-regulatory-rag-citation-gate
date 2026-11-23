/**
 * Wave-Audit-Defect-Fix C3 — ConflictOfInterestPage 신규 page structural test.
 *
 * Plan §6 line 368 acceptance: Playwright + canonical conflict_disclosed +
 * conflict_of_interest_blocked (audit.py:62-63 pre-existing per OQ-2;
 * V057 등록 0건 per plan). Browser-snapshot E2E carries to Wave F4.
 *
 * Here we verify the structural contract: page exists with the 4-endpoint
 * binding (list/detail/create/check) and role gate mirrors backend
 * routers/conflict_of_interest.py POST gate.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SRC = fs.readFileSync(
  path.resolve(__dirname, "../pages/ConflictOfInterestPage.tsx"),
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

describe("C3: ConflictOfInterestPage structural contract", () => {
  it("file exists at canonical location", () => {
    expect(SRC.length).toBeGreaterThan(100);
  });

  it("exports a ConflictOfInterestPage component", () => {
    expect(SRC).toMatch(/export function ConflictOfInterestPage\b/);
  });

  it("binds to GET /conflict-disclosures (list)", () => {
    expect(SRC).toContain('getResource<ListResponse>("/conflict-disclosures")');
  });

  it("binds to POST /conflict-disclosures with the validated payload shape", () => {
    expect(SRC).toContain('postResource<ConflictDisclosureRow>("/conflict-disclosures"');
    // disclosure_from_payload requires disclosure_type/description/chinese_wall_violation
    expect(SRC).toContain("disclosure_type");
    expect(SRC).toContain("chinese_wall_violation");
    expect(SRC).toContain("customer_id");
  });

  it("offers all three disclosure types matching backend allowlist", () => {
    for (const t of ["PRE_TRADE", "POST_TRADE", "RELATED_PARTY"]) {
      expect(SRC).toContain(t);
    }
  });

  it("gates create form on canMutate (AUDIT_VIEWER excluded)", () => {
    expect(SRC).toContain('useAuthStore');
    expect(SRC).toContain('WRITE_ROLES.has(roleCode)');
    expect(SRC).toMatch(/WRITE_ROLES\s*=\s*new Set\(\["PB",\s*"WM",\s*"ADMIN",\s*"BRANCH_MANAGER"\]/);
  });
});

describe("C3: route registration", () => {
  it("App.tsx registers /conflict-of-interest under ProtectedRoute", () => {
    expect(APP).toContain('"/conflict-of-interest"');
    expect(APP).toContain('routeKey="conflictOfInterest"');
    expect(APP).toContain("ConflictOfInterestPage");
  });

  it("access.ts grants PB/WM/BRANCH_MANAGER/ADMIN/AUDIT_VIEWER", () => {
    expect(ACCESS).toMatch(
      /conflictOfInterest:\s*\["PB",\s*"WM",\s*"BRANCH_MANAGER",\s*"ADMIN",\s*"AUDIT_VIEWER"\]/,
    );
  });

  it("types.ts RouteKey includes conflictOfInterest", () => {
    expect(TYPES).toContain('"conflictOfInterest"');
  });
});
