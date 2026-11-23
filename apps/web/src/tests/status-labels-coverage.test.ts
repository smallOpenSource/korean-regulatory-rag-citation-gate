import { describe, expect, it } from "vitest";

import { statusLabel } from "../lib/labels";

/**
 * T3-3 (F15) — STATUS_LABELS coverage gate.
 *
 * 6 surface × DB CHECK enum 전수 → `statusLabel()` lookup이 unmapped fallback
 * (`"상태 미확정 (코드: X)"`)을 반환하지 않는지 검증한다.
 *
 * DB SoT (각 file:LINE):
 *   1. DisputeStatus           — V028__disputes.sql:11
 *   2. EmailDraftsPage         — V034__email_drafts_state_machine.sql:8
 *   3. NbaPage (nba_actions)   — V006__nba_aftercare.sql:8
 *   4. AftercarePage           — V006__nba_aftercare.sql:37 + V036__nba_p1p2p3_aftercare_quarterly.sql:30
 *   5. HouseView lifecycle     — V035__house_view_lifecycle.sql:24 (V004:7 superset)
 *   6. ConsultationGates       — V023__suitability_six_factors.sql:43
 *
 * unmapped fallback이 발생하면 PB perspective 위반 (raw enum 노출 + "코드:" 본문).
 * 신규 enum 추가 시 본 test가 자동 실패하여 STATUS_LABELS 동기화를 강제한다.
 */

interface Surface {
  name: string;
  source: string;
  values: readonly string[];
}

const SURFACES: readonly Surface[] = [
  {
    name: "DisputeStatus",
    source: "V028__disputes.sql:11",
    values: ["OPEN", "RESPONDED", "RESOLVED", "EXPIRED"] as const,
  },
  {
    name: "EmailDraftsPage.status_code",
    source: "V034__email_drafts_state_machine.sql:8",
    values: ["DRAFT", "PENDING_APPROVAL", "APPROVED", "SENT", "FAILED", "CANCELLED"] as const,
  },
  {
    name: "NbaPage.status_code (nba_actions)",
    source: "V006__nba_aftercare.sql:8",
    values: ["PENDING", "IN_PROGRESS", "DONE", "SNOOZED", "DISMISSED"] as const,
  },
  {
    name: "AftercarePage.status_code",
    source: "V006__nba_aftercare.sql:37 + V036__nba_p1p2p3_aftercare_quarterly.sql:30",
    values: ["OPEN", "IN_PROGRESS", "RESOLVED", "PENDING", "COMPLETED", "SKIPPED"] as const,
  },
  {
    name: "HouseView.status_code (lifecycle)",
    source: "V035__house_view_lifecycle.sql:24",
    values: [
      "DRAFT",
      "PENDING_REVIEW",
      "ACTIVE",
      "SUPERSEDED",
      "GENERATED",
      "REVIEWED",
      "ACTIVATED",
      "ARCHIVED",
    ] as const,
  },
  {
    name: "ConsultationGates.gate_status",
    source: "V023__suitability_six_factors.sql:43",
    values: ["PENDING", "PASSED", "BLOCKED", "ACKNOWLEDGED"] as const,
  },
];

describe("STATUS_LABELS coverage — 6 surface × DB CHECK enum (T3-3 F15)", () => {
  for (const surface of SURFACES) {
    describe(`${surface.name} (${surface.source})`, () => {
      for (const value of surface.values) {
        it(`statusLabel("${value}") returns Korean label, not unmapped fallback`, () => {
          const label = statusLabel(value);
          expect(label).not.toContain("미확정");
          expect(label).not.toContain("코드:");
          // sanity: 빈 문자열 / raw enum 자체가 그대로 반환되는 케이스도 fail.
          expect(label.length).toBeGreaterThan(0);
          expect(label).not.toBe(value);
        });
      }
    });
  }

  it("aggregate: 모든 surface 합쳐서 unmapped fallback 0 hit", () => {
    const orphans: { surface: string; value: string; label: string }[] = [];
    for (const surface of SURFACES) {
      for (const value of surface.values) {
        const label = statusLabel(value);
        if (label.includes("미확정") || label.includes("코드:") || label === value) {
          orphans.push({ surface: surface.name, value, label });
        }
      }
    }
    expect(orphans).toEqual([]);
  });
});
