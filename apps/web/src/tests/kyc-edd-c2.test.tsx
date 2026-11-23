/**
 * Wave-Audit-Defect-Fix C2 frontend structural test — KycEddPage 신규.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SRC = fs.readFileSync(
  path.resolve(__dirname, "../pages/KycEddPage.tsx"),
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

describe("C2: KycEddPage structural contract", () => {
  it("exports KycEddPage component", () => {
    expect(SRC).toMatch(/export function KycEddPage\b/);
  });

  it("binds all 5 endpoints", () => {
    expect(SRC).toContain('getResource<ListResponse>("/kyc-edd/triggers")');
    expect(SRC).toContain("/kyc-edd/triggers/${selectedId}"); // detail
    expect(SRC).toContain('postResource<KycEddTrigger>("/kyc-edd/triggers"'); // evaluate
    expect(SRC).toContain("/kyc-edd/triggers/${id}/reassess");
    expect(SRC).toContain("/kyc-edd/triggers/${id}/complete");
  });

  it("gates write actions on canMutate (PB/WM/ADMIN)", () => {
    expect(SRC).toContain("useAuthStore");
    expect(SRC).toContain('WRITE_ROLES = new Set(["PB", "WM", "ADMIN"])');
    expect(SRC).toContain("canMutate");
  });

  it("renders 재평가 + 종결 buttons only when OPEN + canMutate", () => {
    expect(SRC).toContain("재평가");
    expect(SRC).toContain("종결");
    expect(SRC).toMatch(/row\.status === "OPEN"/);
  });
});

describe("C2: route + access registration", () => {
  it("App.tsx registers /kyc-edd under ProtectedRoute", () => {
    expect(APP).toContain('"/kyc-edd"');
    expect(APP).toContain('routeKey="kycEdd"');
    expect(APP).toContain("KycEddPage");
  });

  it("access.ts grants every staff role read", () => {
    expect(ACCESS).toMatch(
      /kycEdd:\s*\["PB",\s*"WM",\s*"BRANCH_MANAGER",\s*"ADMIN",\s*"AUDIT_VIEWER"\]/,
    );
  });

  it("types.ts RouteKey includes kycEdd", () => {
    expect(TYPES).toContain('"kycEdd"');
  });
});
