/**
 * apps/web/src/lib/empty-state-whitelist.ts
 *
 * Single source of truth for routes whose rendered Korean copy is
 * design-intent classified as "uses em-dash / percent in prose,
 * NOT as an empty-state placeholder".
 *
 * Follow-up cycle Wave2-Q1 (svc-follow-up-v1):
 *   - 19 cell hits in audit-out/service-viability-v1/axis-4/placeholder_inventory.json
 *   - 100% confirmed false-positive after DOM-context inspection
 *   - 0 missing-content defects → 0 page text fixes required
 *
 * Audit-script consumption (Python side):
 *   - `scripts/audit_v1_ui_matrix.py` loads the mirror JSON
 *     (`empty-state-whitelist.json`) at module import time and
 *     populates `EMPTY_STATE_WHITELIST_ROUTE_SLUGS` (line ~211).
 *   - When a route's slug appears in the whitelist, `findings["placeholder"]`
 *     is cleared for that cell, eliminating false-positive Axis 4 fails.
 *
 * To keep TS and JSON in sync, this file must mirror `empty-state-whitelist.json`
 * exactly. If you add/remove a route here, update the JSON in the same commit.
 */

/** Intent categories for design-intent placeholder patterns. */
export type PlaceholderIntentType =
  /** Em-dash as separator in titles, e.g. "Subject — Variant". */
  | "em_dash_title_separator"
  /** Em-dash inside aria-label, e.g. "1. 합성 고객 선택 — 대기". */
  | "em_dash_aria_label"
  /** Em-dash inside audit-row text, e.g. "REG-05 T280 — /auth/refresh per-IP 429 차단". */
  | "em_dash_audit_row_separator"
  /** Em-dash inside form placeholder attribute, e.g. "UUID — gate 결과를 …". */
  | "em_dash_form_placeholder"
  /** Compound percent display where "0%" appears as substring, e.g. "100.0%". */
  | "percent_in_compound_metric";

/** Per-route whitelist entry. */
export interface EmptyStateWhitelistEntry {
  /** Stable App.tsx routeKey (lib/access.ts SoT). */
  readonly routeKey: string;
  /** URL-friendly slug used by the audit-script ROUTES inventory. */
  readonly slug: string;
  /** Which design-intent patterns this route legitimately renders. */
  readonly intents: readonly PlaceholderIntentType[];
  /** DOM excerpt or file:LINE pointer for traceability. */
  readonly evidence: string;
}

/**
 * Wave2-Q1 SoT: 8 routes that account for all 19 false-positive
 * placeholder hits in the service-viability cycle.
 *
 * Coverage: 19/19 cells → 8 slugs:
 *   - email-drafts (×3 cells)  : PB1 (×2 phases), WM1
 *   - house-views  (×4 cells)  : PB1, WM1, ADMIN, AUDIT_VIEWER
 *   - conflict-of-interest (×2): PB1, ADMIN
 *   - marketing-review (×3)   : PB1, WM1, ADMIN
 *   - autopilot-demo (×3)     : PB1, WM1, ADMIN
 *   - audit (×2)              : ADMIN, AUDIT_VIEWER
 *   - audit-viewer (×2)       : ADMIN, AUDIT_VIEWER
 *   - batch (×1)              : ADMIN  (percent_in_compound_metric)
 */
export const EMPTY_STATE_WHITELIST: readonly EmptyStateWhitelistEntry[] = [
  {
    routeKey: "emailDrafts",
    slug: "email-drafts",
    intents: ["em_dash_title_separator"],
    evidence:
      "DOM: '[SYN] Service Viability Audit v1 — 상담 안내 (DRAFT 1)' (audit-out PB1__email-drafts.dom.html)",
  },
  {
    routeKey: "houseViews",
    slug: "house-views",
    intents: ["em_dash_title_separator"],
    evidence: "DOM: '[SYN] Service Viability Audit v1 — 대체투자 시각'",
  },
  {
    routeKey: "conflictOfInterest",
    slug: "conflict-of-interest",
    intents: ["em_dash_title_separator"],
    evidence: "DOM: '[SYN] 자사 발행 ETF 추천 — 이해상충 사전공시'",
  },
  {
    routeKey: "marketingReview",
    slug: "marketing-review",
    intents: ["em_dash_title_separator", "em_dash_form_placeholder"],
    evidence: "DOM form placeholder='UUID — gate 결과를 consultation에 반영'",
  },
  {
    routeKey: "autopilotDemo",
    slug: "autopilot-demo",
    intents: ["em_dash_aria_label"],
    evidence: "DOM aria-label='1. 합성 고객 선택 — 대기'",
  },
  {
    routeKey: "audit",
    slug: "audit",
    intents: ["em_dash_audit_row_separator"],
    evidence: "DOM: 'REG-05 T280 — /auth/refresh per-IP 429 차단' (audit row description)",
  },
  {
    routeKey: "auditViewer",
    slug: "audit-viewer",
    intents: ["em_dash_audit_row_separator"],
    evidence: "DOM: 'REG-05 T280 — /auth/refresh per-IP 429 차단'",
  },
  {
    routeKey: "batch",
    slug: "batch",
    intents: ["percent_in_compound_metric"],
    evidence:
      "DOM: '커버리지 비율 100.0%' — detector regex \\b0\\s*%\\b incorrectly matches the '0%' substring inside '100.0%'",
  },
];

/** Set of whitelisted slugs for fast O(1) membership tests. */
export const EMPTY_STATE_WHITELIST_SLUGS: ReadonlySet<string> = new Set(
  EMPTY_STATE_WHITELIST.map((entry) => entry.slug),
);

/** Returns the intent categories for a slug, or empty array if not whitelisted. */
export function intentsForSlug(slug: string): readonly PlaceholderIntentType[] {
  return EMPTY_STATE_WHITELIST.find((entry) => entry.slug === slug)?.intents ?? [];
}

/** Convenience: true when the slug is in the whitelist. */
export function isWhitelistedSlug(slug: string): boolean {
  return EMPTY_STATE_WHITELIST_SLUGS.has(slug);
}
