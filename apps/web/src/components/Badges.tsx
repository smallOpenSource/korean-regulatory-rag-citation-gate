import type { PropsWithChildren } from "react";

import { priorityLabel, statusLabel } from "../lib/labels";

const BADGE_TONES = {
  red: "border-red-200 bg-red-50 text-red-700",
  orange: "border-orange-200 bg-orange-50 text-orange-700",
  yellow: "border-yellow-200 bg-yellow-50 text-yellow-700",
  gray: "border-slate-200 bg-slate-50 text-slate-700",
  green: "border-emerald-200 bg-emerald-50 text-emerald-700",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
} as const;

type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({ tone = "gray", children }: PropsWithChildren<{ tone?: BadgeTone }>) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${BADGE_TONES[tone]}`}>{children}</span>;
}

export function PriorityBadge({ priorityCode }: { priorityCode: string }) {
  const tone = priorityCode === "URGENT" ? "red" : priorityCode === "HIGH" ? "orange" : priorityCode === "MEDIUM" ? "yellow" : "gray";
  return <Badge tone={tone}>{priorityLabel(priorityCode)}</Badge>;
}

const KNOWN_STATUS_GREEN = new Set(["ACTIVE", "APPROVED", "DONE", "FRESH", "ACCEPTED"]);
const KNOWN_STATUS_RED = new Set(["FAILED", "MISSING"]);
const KNOWN_STATUS_ORANGE = new Set([
  "OPEN",
  "SKIPPED",
  "STALE",
  "UNVERIFIED",
  "SYNTHETIC_ONLY",
]);
const KNOWN_STATUS_BLUE = new Set([
  "PENDING",
  "IN_PROGRESS",
  "DRAFT",
  "REVIEWED",
  "SCHEDULED",
]);
// Terminal / neutral states. CLOSED/RESOLVED/DISMISSED/ARCHIVED/CANCELLED
// occupy the same visual tone the KycEddPage list used inline before Q5
// — neutral gray — so the migration to StatusBadge preserves the prior
// reviewer mental model.
const KNOWN_STATUS_GRAY = new Set([
  "CLOSED",
  "RESOLVED",
  "DISMISSED",
  "ARCHIVED",
  "CANCELLED",
]);

function statusBadgeTone(statusCode: string): BadgeTone {
  if (statusCode.includes("READY") || KNOWN_STATUS_GREEN.has(statusCode)) {
    return "green";
  }
  if (statusCode.includes("BLOCKED") || KNOWN_STATUS_RED.has(statusCode)) {
    return "red";
  }
  if (statusCode.includes("DEGRADED") || KNOWN_STATUS_ORANGE.has(statusCode)) {
    return "orange";
  }
  if (KNOWN_STATUS_BLUE.has(statusCode)) {
    return "blue";
  }
  if (KNOWN_STATUS_GRAY.has(statusCode)) {
    return "gray";
  }
  // Wave-Audit-Defect-Fix D-S3: unmapped statusCode is a schema drift signal
  // (the API surfaced a code the UI palette never enumerated). Surface it as
  // red so reviewers see it instead of letting it land on the silent blue
  // fallback that previously masked drift.
  return "red";
}

export function StatusBadge({ statusCode }: { statusCode: string }) {
  const tone = statusBadgeTone(statusCode);
  const label =
    tone === "red" &&
    !KNOWN_STATUS_RED.has(statusCode) &&
    !statusCode.includes("BLOCKED")
      ? `schema_drift (${statusCode})`
      : statusLabel(statusCode);
  return <Badge tone={tone}>{label}</Badge>;
}

import { formatBankerTimestamp } from "../lib/format";

const HIDDEN_MODEL_NAME_RE = /(synthetic[ _-]?qa|ultra[ _-]?qa|golden[ _-]?test|ralph[ _-]?qa|test[ _-]?fixture|모델 대기)/i;
// Wave-Audit-Defect-Fix D-S3: detector regex updated to match the post-D-S1
// canonical 미확정 suffix that format.ts now emits, instead of the legacy
// banned-pattern token.
const PLACEHOLDER_TIMESTAMP_RE = /(생성 대기|모델 대기|준비 중|미확정|^$)/;

// Render the AI provenance badge only when we genuinely have generation
// metadata. When both fields are absent or placeholder copy, return null so
// PB/WM users do not see "AI 생성 · 생성 대기 · 모델 대기" — that placeholder
// stack reads as "the system is broken" rather than "no AI provenance".
export function AiGeneratedBadge({
  generatedAt,
  modelName,
}: {
  generatedAt?: string | null;
  modelName?: string | null;
}) {
  const hasModel = !!modelName && !HIDDEN_MODEL_NAME_RE.test(modelName);
  const hasTimestamp = !!generatedAt && !PLACEHOLDER_TIMESTAMP_RE.test(generatedAt);
  if (!hasModel && !hasTimestamp) {
    return null;
  }
  const timestampLabel = hasTimestamp ? formatBankerTimestamp(generatedAt) : "";
  const parts = ["AI 생성", timestampLabel, hasModel ? modelName : ""].filter(
    (p): p is string => typeof p === "string" && p.length > 0 && !/미확정/.test(p),
  );
  return <Badge tone="blue">{parts.join(" · ")}</Badge>;
}

export function SimulationNotice() {
  return <Badge tone="orange">시뮬레이션 / 실제 주문 아님</Badge>;
}
