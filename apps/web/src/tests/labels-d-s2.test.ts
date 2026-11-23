/**
 * Wave-Audit-Defect-Fix D-S2 — labels.ts must not return the banned PB
 * placeholders (미확인 / 미지정 / 미분류). All 9 *Label() helpers fall back
 * to the canonical 미확정 suffix; unmapped codes surface the raw code so the
 * UI is auditable.
 */

import { describe, expect, it } from "vitest";

import {
  actionTypeLabel,
  eventTypeLabel,
  jobTypeLabel,
  priorityLabel,
  readinessCheckLabel,
  riskGradeLabel,
  segmentLabel,
  sourceLabel,
  statusLabel,
} from "../lib/labels";

const BANNED = /미확인|미지정|미분류/;

describe("D-S2: labels.ts no banned PB placeholders", () => {
  const labelers: Array<[string, (c?: string | null) => string]> = [
    ["statusLabel", statusLabel],
    ["priorityLabel", priorityLabel],
    ["segmentLabel", segmentLabel],
    ["riskGradeLabel", riskGradeLabel],
    ["actionTypeLabel", actionTypeLabel],
    ["eventTypeLabel", eventTypeLabel],
    ["jobTypeLabel", jobTypeLabel],
    ["readinessCheckLabel", readinessCheckLabel],
    ["sourceLabel", sourceLabel],
  ];

  for (const [name, fn] of labelers) {
    it(`${name}(null) returns 미확정 fallback, no banned token`, () => {
      const out = fn(null);
      expect(out).not.toMatch(BANNED);
      expect(out).toContain("미확정");
    });
    it(`${name}(undefined) returns 미확정 fallback, no banned token`, () => {
      const out = fn(undefined);
      expect(out).not.toMatch(BANNED);
      expect(out).toContain("미확정");
    });
    it(`${name}("UNMAPPED_CODE") surfaces the raw code with 미확정 prefix`, () => {
      const out = fn("ZZZ_NOT_REAL");
      expect(out).not.toMatch(BANNED);
      expect(out).toContain("ZZZ_NOT_REAL");
      expect(out).toContain("미확정");
    });
  }
});

describe("D-S2: statusLabel composite (readiness:status form)", () => {
  it("readinessCheckLabel · statusLabel for 'X:Y' input", () => {
    const out = statusLabel("UNK_CHECK:UNK_STATUS");
    expect(out).not.toMatch(BANNED);
    expect(out).toContain("UNK_CHECK");
    expect(out).toContain("UNK_STATUS");
  });
});
