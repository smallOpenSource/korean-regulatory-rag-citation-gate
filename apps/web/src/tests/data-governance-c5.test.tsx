/**
 * Wave-Audit-Defect-Fix C5 — DataGovernancePage 신규 page structural test.
 *
 * Plan §6 line 370: 3 endpoints (POST/GET /purge-schedule + GET
 * /pseudonym-metadata). Backend POST emits the established canonical
 * `credit_info_purge_simulated` (audit.py:72) — `purge_schedule_created`
 * and `pseudonym_metadata_viewed` mentioned in plan §6 land under Wave C
 * C2 scope (V060). No new migration in this commit.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SRC = fs.readFileSync(
  path.resolve(__dirname, "../pages/DataGovernancePage.tsx"),
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

describe("C5: DataGovernancePage structural contract", () => {
  it("file exists at canonical location", () => {
    expect(SRC.length).toBeGreaterThan(100);
  });

  it("exports DataGovernancePage component", () => {
    expect(SRC).toMatch(/export function DataGovernancePage\b/);
  });

  it("binds all 3 endpoints (GET /pseudonym-metadata, GET + POST /purge-schedule)", () => {
    expect(SRC).toContain('getResource<PseudonymMetadataResponse>("/data-governance/pseudonym-metadata")');
    expect(SRC).toContain('getResource<PurgeScheduleListResponse>("/data-governance/purge-schedule")');
    expect(SRC).toContain('postResource<PurgeScheduleRow>("/data-governance/purge-schedule"');
  });

  it("gates purge create form on ADMIN only (canCreatePurge)", () => {
    expect(SRC).toContain("useAuthStore");
    expect(SRC).toMatch(/canCreatePurge\s*=\s*roleCode\s*===\s*"ADMIN"/);
    // Form must be wrapped in {canCreatePurge && (
    expect(SRC).toMatch(/\{canCreatePurge\s*&&\s*\(/);
  });

  it("pseudonym metadata renders both label and risk note", () => {
    expect(SRC).toContain("pseudonym_label");
    expect(SRC).toContain("reidentification_risk_note");
  });

  it("purge form fields match backend POST contract", () => {
    for (const field of ["customer_id", "target_table", "target_row_id", "reason"]) {
      expect(SRC).toContain(field);
    }
  });
});

describe("C5: route + access registration", () => {
  it("App.tsx registers /data-governance under ProtectedRoute", () => {
    expect(APP).toContain('"/data-governance"');
    expect(APP).toContain('routeKey="dataGovernance"');
    expect(APP).toContain("DataGovernancePage");
  });

  it("access.ts grants all staff roles read; ADMIN-gated write inside page", () => {
    expect(ACCESS).toMatch(
      /dataGovernance:\s*\["PB",\s*"WM",\s*"BRANCH_MANAGER",\s*"ADMIN",\s*"AUDIT_VIEWER"\]/,
    );
  });

  it("types.ts RouteKey includes dataGovernance", () => {
    expect(TYPES).toContain('"dataGovernance"');
  });
});
