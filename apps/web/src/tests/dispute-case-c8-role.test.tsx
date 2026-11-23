/**
 * Wave-Audit-Defect-Fix C8 — DisputeCasePage role-aware visibility.
 *
 * Mirrors the C7 backend role gate (routers/disputes.py):
 *   - AUDIT_VIEWER: list/read only; "답변 처리" / "해결 처리" + 시드 버튼 hidden
 *   - PB / WM: can advance status (mutate)
 *   - ADMIN: can advance status + see seed button
 *
 * Structural test: introspect the source for the gating idiom rather than
 * boot the full page (which would require API/network mocks).
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const PAGE = fs.readFileSync(
  path.resolve(__dirname, "../pages/DisputeCasePage.tsx"),
  "utf-8",
);

describe("C8: DisputeCasePage role-aware UI", () => {
  it("imports useAuthStore (was hardcoded placeholder)", () => {
    expect(PAGE).toContain('from "../store/auth"');
    expect(PAGE).toContain("useAuthStore");
  });

  it("derives roleCode from the auth store, not from useState(false)", () => {
    expect(PAGE).toMatch(/const\s+roleCode\s*=/);
    // The old `const [isAdmin] = useState(false)` line must be gone.
    expect(PAGE).not.toMatch(/const\s+\[isAdmin\]\s*=\s*useState\(false\)/);
  });

  it("computes canMutate gate over PB/WM/ADMIN (AUDIT_VIEWER excluded)", () => {
    expect(PAGE).toContain('roleCode === "PB"');
    expect(PAGE).toContain('roleCode === "WM"');
    expect(PAGE).toContain('roleCode === "ADMIN"');
    expect(PAGE).not.toMatch(/roleCode\s*===\s*"AUDIT_VIEWER"/);
  });

  it("gates the advance-status button on canMutate", () => {
    expect(PAGE).toContain('canMutate && (');
    // Specifically the advance/seed flow:
    expect(PAGE).toContain('advanceStatus');
  });

  it("gates the seed button on isAdmin (preserved from prior code)", () => {
    expect(PAGE).toMatch(/\{isAdmin\s*&&\s*\(/);
    expect(PAGE).toContain("seedSyntheticCase");
  });
});
