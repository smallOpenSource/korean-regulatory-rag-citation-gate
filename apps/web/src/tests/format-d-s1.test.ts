/**
 * Wave-Audit-Defect-Fix D-S1 — formatBankerTimestamp / formatBankerNumber
 * must no longer return the banned PB-perspective placeholders ("—" / "미확인"
 * / "미지정" / "미분류"). Plan §6 acceptance: grep banned tokens 0건.
 */

import { describe, expect, it } from "vitest";

import {
  formatBankerNumber,
  formatBankerTimestamp,
  formatKRW,
} from "../lib/format";

describe("D-S1: formatBankerTimestamp", () => {
  it("returns explicit diagnostic label, not em-dash, on null input", () => {
    expect(formatBankerTimestamp(null)).toBe("시각 미확정");
  });
  it("returns explicit diagnostic label, not em-dash, on undefined input", () => {
    expect(formatBankerTimestamp(undefined)).toBe("시각 미확정");
  });
  it("returns explicit diagnostic label, not em-dash, on unparseable input", () => {
    expect(formatBankerTimestamp("not-a-timestamp")).toBe("시각 미확정");
  });
  it("returns the formatted timestamp on valid ISO input", () => {
    const result = formatBankerTimestamp("2026-05-21T08:30:00Z");
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });
});

describe("D-S1: formatBankerNumber", () => {
  it("returns explicit diagnostic label on undefined", () => {
    expect(formatBankerNumber(undefined)).toBe("수치 미확정");
  });
  it("returns explicit diagnostic label on null", () => {
    expect(formatBankerNumber(null)).toBe("수치 미확정");
  });
  it("returns 0 for the integer zero (not the fallback)", () => {
    expect(formatBankerNumber(0)).toBe("0");
  });
  it("returns formatted value with unit suffix", () => {
    expect(formatBankerNumber(42, "건")).toBe("42건");
  });
});

describe("D-S1: formatKRW (regression — was not in scope, must still work)", () => {
  it("returns '정보 없음' on null", () => {
    expect(formatKRW(null)).toBe("정보 없음");
  });
  it("returns abbreviated unit for >= 1억", () => {
    expect(formatKRW(720000000)).toBe("7억원");
  });
});
