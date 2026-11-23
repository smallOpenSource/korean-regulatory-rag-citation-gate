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
}

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
  if (id.length > 12) return `${id.slice(0, 8)}…`;
  return id;
}

function actorDisplay(log: AuditLog): string {
  if (log.actor_name) {
    return log.actor_employee_no ? `${log.actor_name} (${log.actor_employee_no})` : log.actor_name;
  }
  return log.actor_employee_no ?? "시스템";
}

export function AuditPage() {
  const logs = useQuery({
    queryKey: ["audit-logs"],
    queryFn: () => getResource<ListResponse<AuditLog>>("/audit-logs"),
  });
  const items = logs.data?.items ?? [];
  return (
    <ApiPanel title="감사 로그 조회" error={logs.error}>
      <div className="overflow-hidden rounded-2xl border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="p-3">업무</th>
              <th className="p-3">리소스</th>
              <th className="p-3">수행자</th>
              <th className="p-3">생성 시각</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {items.map((log) => (
              <tr key={log.id}>
                <td className="p-3 font-semibold" title={log.action_code}>
                  {log.action_description ?? log.action_code}
                </td>
                <td className="p-3" title={`${log.resource_type ?? "?"}:${log.resource_id ?? "?"}`}>
                  {resourceTypeLabel(log.resource_type)}
                  <span className="ml-1 font-mono text-xs text-slate-400">{shortId(log.resource_id)}</span>
                </td>
                <td className="p-3" title={log.actor_id ?? ""}>
                  {actorDisplay(log)}
                </td>
                <td className="p-3 tabular-nums">{formatBankerTimestamp(log.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 ? (
          <p className="p-5 text-sm text-slate-500">감사 로그가 없습니다. AUDIT_VIEWER는 읽기 전용입니다.</p>
        ) : null}
      </div>
    </ApiPanel>
  );
}
