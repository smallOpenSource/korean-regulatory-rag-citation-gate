/**
 * Korean banker-friendly formatters for display.
 *
 * - formatBankerTimestamp(iso) — "2026-04-20 13:52" (Asia/Seoul, no seconds/microseconds)
 * - formatBankerNumber(n, unit?) — "42건" / "1,250" with thousands separator
 */

const SEOUL_TZ_OFFSET_MIN = 9 * 60; // Asia/Seoul (no DST)

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

// PostgreSQL serializes timestamptz as e.g. `2026-05-16 14:52:16.847752+00`:
// space separator, sub-millisecond precision, and timezone offset without a
// colon. JavaScript's Date constructor returns Invalid Date for that exact
// shape, so we normalize to ISO-8601 before parsing. Banker UI must never
// leak raw microseconds or `+00` short offset to the screen.
function normalizeTimestamp(value: string): string {
  let normalized = value.trim();
  if (normalized.includes(" ") && !normalized.includes("T")) {
    normalized = normalized.replace(" ", "T");
  }
  normalized = normalized.replace(/\.(\d{3})\d+/, ".$1");
  normalized = normalized.replace(/([+-]\d{2})$/, "$1:00");
  return normalized;
}

/**
 * Format an ISO-8601 (or PostgreSQL timestamptz) value for PB/WM display:
 * `YYYY-MM-DD HH:mm` in Korea Standard Time. Seconds and microseconds are
 * dropped, the timezone offset is hidden.
 *
 * Wave-Audit-Defect-Fix D-S1: when the value is missing or unparseable the
 * function returns the explicit label "시각 미확정" instead of the em-dash
 * placeholder, so PB users see a visible diagnostic instead of a glyph that
 * silently blends into table cells.
 */
export function formatBankerTimestamp(value: string | null | undefined): string {
  if (!value) return "시각 미확정";
  const date = new Date(normalizeTimestamp(String(value)));
  if (Number.isNaN(date.getTime())) {
    return "시각 미확정";
  }
  const seoul = new Date(date.getTime() + SEOUL_TZ_OFFSET_MIN * 60_000);
  // Use UTC accessors after the offset shift so we present Asia/Seoul time
  // independent of the browser's local timezone.
  const year = seoul.getUTCFullYear();
  const month = pad2(seoul.getUTCMonth() + 1);
  const day = pad2(seoul.getUTCDate());
  const hours = pad2(seoul.getUTCHours());
  const minutes = pad2(seoul.getUTCMinutes());
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/**
 * Format an integer (count) for display with optional Korean unit suffix.
 *
 * Wave-Audit-Defect-Fix D-S1: the missing-value branch now returns an explicit
 * diagnostic label (suffixed 미확정) instead of the ambiguous banned-pattern
 * fallback, so PB users can distinguish an unfetched number from zero.
 *
 * - `formatBankerNumber(0)` → `"0"`
 * - `formatBankerNumber(42, "건")` → `"42건"`
 * - `formatBankerNumber(1_250)` → `"1,250"`
 * - `formatBankerNumber(undefined)` → `"수치 미확정"`
 */
export function formatBankerNumber(
  value: number | null | undefined,
  unit?: string,
): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "수치 미확정";
  }
  const formatted = value.toLocaleString("ko-KR");
  return unit ? `${formatted}${unit}` : formatted;
}

/**
 * Format a Korean won amount for banker UX with abbreviated units.
 *
 * Backend serializes Decimal as a JSON string (e.g. "7200000000.00"), so this
 * accepts both number and string forms. Enterprise WM convention: 1조 이상은
 * "1.2조원", 1억 이상은 "72억원", 1만 이상은 "1,250만원", 미만은 "1,250원".
 * Returns "정보 없음" when the value is missing or unparseable — banker UI must
 * never leak raw decimal scale like "7200000000.00원".
 */
export function formatKRW(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "정보 없음";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "정보 없음";
  const sign = n < 0 ? "-" : "";
  const abs = Math.round(Math.abs(n));
  const TRILLION = 1_0000_0000_0000;
  const EOK = 1_0000_0000;
  const MAN = 1_0000;
  if (abs >= TRILLION) {
    const v = abs / TRILLION;
    return `${sign}${v.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}조원`;
  }
  if (abs >= EOK) {
    const v = Math.round(abs / EOK);
    return `${sign}${v.toLocaleString("ko-KR")}억원`;
  }
  if (abs >= MAN) {
    const v = Math.round(abs / MAN);
    return `${sign}${v.toLocaleString("ko-KR")}만원`;
  }
  return `${sign}${abs.toLocaleString("ko-KR")}원`;
}
