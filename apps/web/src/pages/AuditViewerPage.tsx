/**
 * AuditViewerPage — T252
 *
 * AUDIT_VIEWER / ADMIN only.
 * Filter by action_code, actor_id, date range.
 * Pagination 50/page. Export to CSV.
 * Audit hash placeholder for retention chain.
 */

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiPanel } from "../components/ApiPanel";
import { getResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import type { ListResponse } from "../lib/types";

interface AuditLog {
  id: string;
  actor_id?: string;
  actor_name?: string;
  actor_employee_no?: string;
  action_code: string;
  action_description?: string;
  resource_type?: string;
  resource_id?: string;
  created_at: string;
  audit_hash?: string;
}

const PAGE_SIZE = 50;

const RESOURCE_TYPE_KO: Record<string, string> = {
  consultation: "상담",
  customer: "고객",
  email_draft: "이메일 초안",
  email_drafts: "이메일 초안",
  house_view: "하우스뷰",
  nba_action: "NBA",
  nba_card: "NBA 카드",
  nba_actions: "NBA",
  aftercare_event: "사후관리 이벤트",
  ws_ticket: "WS 티켓",
  ws_connection: "WS 연결",
  audit_log: "감사 로그",
  ai_output: "AI 출력",
  ai_job: "AI 작업",
  document: "문서",
  document_chunk: "문서 청크",
  kyc_edd_trigger: "KYC EDD 트리거",
  marketing_review: "마케팅 심의",
  dispute: "분쟁",
  conflict_disclosure: "이해상충 공시",
  consent: "동의",
  rights_notice: "권리 고지",
  info_access_request: "자료요구 응답",
};

function resourceTypeLabel(code?: string): string {
  if (!code) return "기타";
  return RESOURCE_TYPE_KO[code] ?? code;
}

function shortId(id?: string): string {
  if (!id) return "";
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

function actorDisplay(log: AuditLog): string {
  if (log.actor_name) {
    return log.actor_employee_no ? `${log.actor_name} (${log.actor_employee_no})` : log.actor_name;
  }
  return log.actor_employee_no ?? "시스템";
}

function buildCsv(rows: AuditLog[]): string {
  const header = ["id", "action_code", "resource_type", "resource_id", "actor_id", "created_at", "audit_hash"];
  const lines = rows.map((r) =>
    [r.id, r.action_code, r.resource_type ?? "", r.resource_id ?? "", r.actor_id ?? "", r.created_at, r.audit_hash ?? ""].join(","),
  );
  return [header.join(","), ...lines].join("\n");
}

function downloadCsv(content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function AuditViewerPage() {
  const [actionFilter, setActionFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const tableRef = useRef<HTMLTableElement>(null);

  const logs = useQuery({
    queryKey: ["audit-logs-viewer"],
    queryFn: () => getResource<ListResponse<AuditLog>>("/audit-logs"),
  });

  const allItems = logs.data?.items ?? [];

  const filtered = allItems.filter((log) => {
    const matchAction = actionFilter === "" || log.action_code.toLowerCase().includes(actionFilter.toLowerCase());
    const matchActor = actorFilter === "" || (log.actor_id ?? "").toLowerCase().includes(actorFilter.toLowerCase());
    const matchFrom = dateFrom === "" || log.created_at >= dateFrom;
    const matchTo = dateTo === "" || log.created_at <= dateTo + "T23:59:59";
    return matchAction && matchActor && matchFrom && matchTo;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageItems = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  function handleReset() {
    setActionFilter("");
    setActorFilter("");
    setDateFrom("");
    setDateTo("");
    setPage(0);
  }

  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-slate-800 to-slate-950 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-slate-400">거버넌스 · 감사</p>
        <h1 className="mt-3 text-3xl font-black">감사 로그 열람</h1>
        <p className="mt-2 text-slate-300 text-sm">감사 이력 조회 · 필터링 · CSV 내보내기 (AUDIT_VIEWER 전용)</p>
      </section>

      {/* Retention policy — T209 자료유지·열람 SEC-02 §보존기간 reference */}
      <section
        aria-label="자료유지 및 보존 정책"
        className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"
      >
        <h2 className="font-semibold text-blue-950">자료유지 · 보존 정책</h2>
        <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="font-bold">감사 로그 (audit_logs)</dt>
            <dd className="text-blue-800">10년 (append-only, V008+V019 트리거)</dd>
          </div>
          <div>
            <dt className="font-bold">AI 출력 (ai_outputs)</dt>
            <dd className="text-blue-800">5년 (fail_closed 사유 포함 retention)</dd>
          </div>
          <div>
            <dt className="font-bold">상담 게이트 증빙</dt>
            <dd className="text-blue-800">10년 (상담 종료일 기준)</dd>
          </div>
          <div>
            <dt className="font-bold">이메일 초안 (email_drafts)</dt>
            <dd className="text-blue-800">5년 (발송/거부 사유 포함)</dd>
          </div>
          <div>
            <dt className="font-bold">자료요구 응답 (info_access)</dt>
            <dd className="text-blue-800">5년 (요청자 신원 + 응답 결과)</dd>
          </div>
          <div>
            <dt className="font-bold">신용정보 (credit_info)</dt>
            <dd className="text-blue-800">5년 (신용정보법 §40-2)</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-blue-700">
          상세 정책은{" "}
          <a
            href="/docs/security/SEC-02_data_privacy.md"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold underline hover:text-blue-900"
          >
            SEC-02 데이터 프라이버시
          </a>{" "}
          및 금소법 §28 (자료유지·열람권) 을 따릅니다. AUDIT_VIEWER 역할은 조회·내보내기 권한만 보유합니다 (수정 불가).
        </p>
      </section>

      {/* Filters */}
      <section
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        aria-label="감사 로그 필터"
      >
        <h2 className="mb-4 text-base font-semibold text-slate-900">필터</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor="filter-action" className="mb-1.5 block text-xs font-semibold text-slate-600">
              업무 코드 (action_code)
            </label>
            <input
              id="filter-action"
              type="text"
              value={actionFilter}
              onChange={(e) => { setActionFilter(e.target.value); setPage(0); }}
              placeholder="예: NBA_GENERATED"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
              aria-label="업무 코드 필터"
            />
          </div>
          <div>
            <label htmlFor="filter-actor" className="mb-1.5 block text-xs font-semibold text-slate-600">
              수행자 ID (actor_id)
            </label>
            <input
              id="filter-actor"
              type="text"
              value={actorFilter}
              onChange={(e) => { setActorFilter(e.target.value); setPage(0); }}
              placeholder="예: emp-001"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
              aria-label="수행자 ID 필터"
            />
          </div>
          <div>
            <label htmlFor="filter-from" className="mb-1.5 block text-xs font-semibold text-slate-600">
              시작일
            </label>
            <input
              id="filter-from"
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(0); }}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
              aria-label="시작일 필터"
            />
          </div>
          <div>
            <label htmlFor="filter-to" className="mb-1.5 block text-xs font-semibold text-slate-600">
              종료일
            </label>
            <input
              id="filter-to"
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(0); }}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
              aria-label="종료일 필터"
            />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleReset}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
          >
            필터 초기화
          </button>
          <button
            type="button"
            onClick={() => downloadCsv(buildCsv(filtered))}
            disabled={filtered.length === 0}
            aria-label="필터된 감사 로그를 CSV로 내보내기"
            className="rounded-xl bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
          >
            CSV 내보내기 ({filtered.length}건)
          </button>
          <p className="ml-auto text-xs text-slate-500" aria-live="polite">
            전체 {allItems.length}건 중 {filtered.length}건 표시
          </p>
        </div>
      </section>

      {/* Table */}
      <ApiPanel title="감사 이력" error={logs.error}>
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table
            ref={tableRef}
            className="min-w-full divide-y divide-slate-100 text-sm"
            aria-label="감사 로그 목록"
            aria-rowcount={filtered.length}
          >
            <thead className="bg-slate-50">
              <tr>
                {[
                  ["업무 코드", "action_code"],
                  ["리소스", "resource"],
                  ["수행자", "actor_id"],
                  ["생성 시각", "created_at"],
                  ["감사 해시", "audit_hash"],
                ].map(([label, key]) => (
                  <th
                    key={key}
                    scope="col"
                    className="p-3 text-left text-xs font-bold uppercase tracking-wide text-slate-500"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {pageItems.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-sm text-slate-500">
                    {logs.isPending ? "데이터를 불러오는 중..." : "조건에 맞는 감사 로그가 없습니다."}
                  </td>
                </tr>
              ) : (
                pageItems.map((log, idx) => (
                  <tr key={log.id} aria-rowindex={page * PAGE_SIZE + idx + 1} className="hover:bg-slate-50">
                    <td className="p-3" title={log.action_code}>
                      <span className="font-semibold text-slate-900">
                        {log.action_description ?? log.action_code}
                      </span>
                    </td>
                    <td className="p-3 text-slate-700" title={`${log.resource_type ?? "?"}:${log.resource_id ?? "?"}`}>
                      <span className="font-medium">{resourceTypeLabel(log.resource_type)}</span>
                      <span className="ml-1 font-mono text-xs text-slate-400">{shortId(log.resource_id)}</span>
                    </td>
                    <td className="p-3 text-slate-700" title={log.actor_id ?? ""}>
                      {actorDisplay(log)}
                    </td>
                    <td className="p-3 text-slate-600 tabular-nums">{formatBankerTimestamp(log.created_at)}</td>
                    <td className="p-3">
                      <code className="font-mono text-xs text-slate-400" title="감사 해시 (보존 체인 플레이스홀더)">
                        {log.audit_hash ? log.audit_hash.slice(0, 12) + "…" : "해시 미생성"}
                      </code>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <nav
            className="mt-4 flex items-center justify-between gap-3"
            aria-label="감사 로그 페이지 탐색"
          >
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              aria-label="이전 페이지"
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-40 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
            >
              ← 이전
            </button>
            <p className="text-sm text-slate-600" aria-current="page">
              {page + 1} / {totalPages} 페이지
            </p>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
              aria-label="다음 페이지"
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-40 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
            >
              다음 →
            </button>
          </nav>
        )}
      </ApiPanel>
    </div>
  );
}
