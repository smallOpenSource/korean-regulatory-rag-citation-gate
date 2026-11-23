/**
 * Quarantine Dashboard — REG-04 T243 V032
 * Lists document_chunks with quarantine_flag=true.
 * Shows quarantine_reason_code + created_at.
 * ADMIN can release (writes quarantine_released audit event).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badges";
import { DevReference } from "../components/DevReference";
import { getResource, postResource } from "../lib/api";
import type { ListResponse } from "../lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QuarantineChunk {
  id: string;
  document_id?: string;
  chunk_index?: number;
  quarantine_flag: boolean;
  quarantine_reason_code?: string;
  quarantine_reviewed_at?: string | null;
  created_at?: string;
}

interface QuarantineMetrics {
  quarantine_flag_count: number;
  quarantine_reviewed_count: number;
  quarantine_schema_ready: number;
}

interface DocumentChunksResponse extends ListResponse<QuarantineChunk> {
  quarantine_metrics: QuarantineMetrics;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const REASON_LABELS: Record<string, string> = {
  PROMPT_INJECTION: "프롬프트 인젝션",
  LOW_FAITHFULNESS: "신뢰도 부족",
  CONTENT_SAFETY: "콘텐츠 안전 위반",
  QUARANTINE_PATTERN: "격리 패턴 매칭",
  DIMENSION_MISMATCH: "벡터 차원 불일치",
};

function reasonLabel(code: string | undefined): string {
  if (!code) return "사유 미확인";
  return REASON_LABELS[code] ?? code;
}

function reasonTone(code: string | undefined): "red" | "orange" | "yellow" | "gray" {
  if (!code) return "gray";
  if (code.includes("INJECTION") || code.includes("SAFETY")) return "red";
  if (code.includes("FAITHFULNESS") || code.includes("PATTERN")) return "orange";
  return "yellow";
}

// Wave-Audit-Defect-Fix D-S4: delegate to formatBankerTimestamp (single
// canonical helper). Local raw Date-format site removed per
// page-level-consistency-grep.
import { formatBankerTimestamp } from "../lib/format";

function formatDateShort(iso: string | undefined | null): string {
  return formatBankerTimestamp(iso);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-black text-slate-950 tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function QuarantineDashboard() {
  const queryClient = useQueryClient();

  const chunks = useQuery({
    queryKey: ["quarantine-chunks"],
    queryFn: () =>
      getResource<DocumentChunksResponse>("/document-chunks?quarantine_flag=true&limit=100"),
  });

  const releaseMutation = useMutation({
    mutationFn: (chunkId: string) =>
      postResource<QuarantineChunk>(`/document-chunks/${chunkId}/release`),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["quarantine-chunks"] }),
  });

  const items = chunks.data?.items ?? [];
  const metrics = chunks.data?.quarantine_metrics;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <DevReference inline="REG-04" />
          <h1 className="mt-1 text-2xl font-black text-slate-950">격리 대시보드</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            문서 청크 격리 항목 검토 · V032 · <DevReference inline="ADR-005 Dual-LLM Quarantine" />
          </p>
        </div>
        <Badge tone="red">관리자 전용</Badge>
      </div>

      {/* Metrics */}
      {metrics && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard
            label="격리 항목"
            value={metrics.quarantine_flag_count}
            sub="격리 플래그 활성"
          />
          <MetricCard
            label="검토 완료"
            value={metrics.quarantine_reviewed_count}
            sub="검토 일시 기록됨"
          />
          <MetricCard
            label="미검토"
            value={Math.max(0, metrics.quarantine_flag_count - metrics.quarantine_reviewed_count)}
            sub="검토 필요"
          />
          <MetricCard
            label="스키마 상태"
            value={metrics.quarantine_schema_ready > 0 ? "준비됨" : "미적용"}
            sub="V032 마이그레이션"
          />
        </div>
      )}

      {/* Error / loading */}
      {chunks.isLoading && (
        <p className="py-6 text-center text-sm text-slate-400">격리 항목 불러오는 중…</p>
      )}
      {chunks.error && (
        <p role="alert" className="rounded-xl bg-amber-50 p-4 text-sm text-amber-800">
          격리 데이터를 불러오지 못했습니다.
        </p>
      )}
      {releaseMutation.error && (
        <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">
          해제 처리 중 오류가 발생했습니다.
        </p>
      )}

      {/* Table */}
      {!chunks.isLoading && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {items.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12">
              <svg className="size-8 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm font-semibold text-slate-700">격리된 청크가 없습니다</p>
              <p className="text-xs text-slate-400">모든 문서 청크가 정상 상태입니다.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" role="table" aria-label="격리된 문서 청크 목록">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-bold uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3">청크 ID</th>
                    <th className="px-4 py-3">문서 ID</th>
                    <th className="px-4 py-3">청크 인덱스</th>
                    <th className="px-4 py-3">격리 사유 코드</th>
                    <th className="px-4 py-3">검토 일시</th>
                    <th className="px-4 py-3">생성 일시</th>
                    <th className="px-4 py-3">조치</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((chunk) => {
                    const isReleased = !chunk.quarantine_flag || Boolean(chunk.quarantine_reviewed_at);
                    return (
                      <tr key={chunk.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono text-xs text-slate-600">
                          {chunk.id.slice(0, 8)}…
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-slate-600">
                          {chunk.document_id ? `${chunk.document_id.slice(0, 8)}…` : "-"}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-slate-700">
                          #{chunk.chunk_index ?? "-"}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={reasonTone(chunk.quarantine_reason_code)}>
                            {reasonLabel(chunk.quarantine_reason_code)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500">
                          {chunk.quarantine_reviewed_at ? (
                            <span className="text-emerald-600 font-semibold">
                              {formatDateShort(chunk.quarantine_reviewed_at)}
                            </span>
                          ) : (
                            <span className="text-amber-600">미검토</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500">
                          {formatDateShort(chunk.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          {isReleased ? (
                            <span className="text-xs text-emerald-600 font-semibold">해제됨</span>
                          ) : (
                            <button
                              type="button"
                              disabled={releaseMutation.isPending}
                              onClick={() => releaseMutation.mutate(chunk.id)}
                              className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                              aria-label={`청크 ${chunk.id.slice(0, 8)} 격리 해제`}
                            >
                              격리 해제
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Footer note */}
      <p className="text-xs text-slate-400">
        격리 해제 시 감사 로그에 격리 해제 이벤트가 기록됩니다.
      </p>
    </div>
  );
}
