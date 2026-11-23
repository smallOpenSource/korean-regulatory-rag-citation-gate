/**
 * 이메일 초안 (Email Drafts state machine — ADR-002 W1)
 *
 * DRAFT → PENDING_APPROVAL → APPROVED → SENT | FAILED
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getResource, postResource } from "../lib/api";
import { useAuthStore } from "../store/auth";

interface EmailDraft {
  id: string;
  draft_id: string;
  customer_id: string;
  consultation_id: string | null;
  // T3-3 (F15): DB SoT V034:8 CHECK (status_code IN ('DRAFT','PENDING_APPROVAL',
  // 'APPROVED','SENT','FAILED','CANCELLED')). CANCELLED는 사용자/시스템 cancel
  // path emit이므로 frontend type/label/palette가 누락되면 raw enum 노출.
  status_code: "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "SENT" | "FAILED" | "CANCELLED";
  subject: string;
  body: string;
  marketing_classified: boolean;
  created_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  failure_reason_code: string | null;
}

interface DraftListResponse {
  items: EmailDraft[];
  limit: number;
  offset: number;
}

const STATUS_LABELS: Record<EmailDraft["status_code"], string> = {
  DRAFT: "초안",
  PENDING_APPROVAL: "승인 대기",
  APPROVED: "승인 완료",
  SENT: "발송 완료",
  FAILED: "발송 실패",
  CANCELLED: "취소",
};

const STATUS_PALETTE: Record<EmailDraft["status_code"], string> = {
  DRAFT: "bg-slate-100 text-slate-700",
  PENDING_APPROVAL: "bg-amber-100 text-amber-800",
  APPROVED: "bg-blue-100 text-blue-800",
  SENT: "bg-emerald-100 text-emerald-800",
  FAILED: "bg-rose-100 text-rose-800",
  CANCELLED: "bg-slate-200 text-slate-600",
};

const STATUS_ORDER: EmailDraft["status_code"][] = [
  "DRAFT",
  "PENDING_APPROVAL",
  "APPROVED",
  "SENT",
  "FAILED",
  "CANCELLED",
];

function formatLocalTimestamp(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

export function EmailDraftsPage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [statusFilter, setStatusFilter] = useState<EmailDraft["status_code"] | "ALL">("ALL");
  const canMutate = user?.roleCode === "PB" || user?.roleCode === "WM";

  const drafts = useQuery({
    queryKey: ["email-drafts", statusFilter],
    queryFn: () => {
      const query = statusFilter === "ALL" ? "" : `?status_code=${statusFilter}`;
      return getResource<DraftListResponse>(`/email-drafts${query}`);
    },
  });

  const items = useMemo<EmailDraft[]>(() => drafts.data?.items ?? [], [drafts.data]);

  const transition = useMutation({
    mutationFn: ({
      draftId,
      op,
      reason,
    }: {
      draftId: string;
      op: "submit" | "approve" | "reject" | "send";
      reason?: string;
    }) => {
      const body = op === "reject" && reason ? { reason } : undefined;
      // ADR-011 / V063: all four POST transitions are decorated with
      // @idempotent server-side and require an Idempotency-Key header.
      // Generate a fresh UUID per click so retries (network blip, user
      // double-click) replay rather than create duplicate state moves.
      return postResource<EmailDraft>(
        `/email-drafts/${draftId}/${op}`,
        body,
        { idempotencyKey: crypto.randomUUID() },
      );
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["email-drafts"] }),
  });

  return (
    <section className="grid gap-6">
      <header className="rounded-3xl bg-gradient-to-br from-indigo-700 via-purple-700 to-fuchsia-600 p-7 text-white shadow-md">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-100">고객 이메일 초안 승인 절차</p>
        <h1 className="mt-2 text-2xl font-black">이메일 초안</h1>
        <p className="mt-3 max-w-3xl text-indigo-50">
          AI가 생성한 이메일 초안을 직원이 검토·승인한 뒤에만 발송됩니다.
          작성, 승인 요청, 승인 완료, 발송 단계가 모두 감사 로그에 기록됩니다.
        </p>
      </header>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong className="font-bold">합성 데이터</strong> · 고객·메일 본문은 합성 데이터이며, 실제 발송은 내부 샌드박스(Mailpit)로만 전송됩니다.
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-700">상태 필터</span>
        <button
          type="button"
          onClick={() => setStatusFilter("ALL")}
          className={`rounded-full px-3 py-1.5 text-xs font-bold ${
            statusFilter === "ALL" ? "bg-blue-700 text-white" : "border border-slate-300 text-slate-700 hover:bg-slate-100"
          }`}
        >
          전체
        </button>
        {STATUS_ORDER.map((code) => (
          <button
            type="button"
            key={code}
            onClick={() => setStatusFilter(code)}
            className={`rounded-full px-3 py-1.5 text-xs font-bold ${
              statusFilter === code ? "bg-blue-700 text-white" : "border border-slate-300 text-slate-700 hover:bg-slate-100"
            }`}
          >
            {STATUS_LABELS[code]}
          </button>
        ))}
      </div>

      {drafts.isLoading && <p className="text-sm text-slate-500">정보를 불러오는 중입니다.</p>}
      {drafts.error && (
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          이메일 초안 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
        </p>
      )}

      {items.length === 0 && !drafts.isLoading && !drafts.error && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          표시할 이메일 초안이 없습니다. 고객 상담 화면에서 새 초안을 만들어 보세요.
        </div>
      )}

      <ul className="grid gap-3">
        {items.map((draft) => (
          <li
            key={draft.id}
            className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="grid gap-1">
                <p className="text-sm font-semibold text-slate-900">{draft.subject || "(제목 없음)"}</p>
                <p className="text-xs text-slate-500">
                  생성 {formatLocalTimestamp(draft.created_at)}
                  {draft.submitted_at && ` · 승인 요청 ${formatLocalTimestamp(draft.submitted_at)}`}
                  {draft.approved_at && ` · 승인 ${formatLocalTimestamp(draft.approved_at)}`}
                  {draft.sent_at && ` · 발송 ${formatLocalTimestamp(draft.sent_at)}`}
                </p>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_PALETTE[draft.status_code]}`}>
                {STATUS_LABELS[draft.status_code]}
              </span>
            </div>

            <p className="line-clamp-3 whitespace-pre-line rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
              {draft.body || "(본문 없음)"}
            </p>

            {draft.marketing_classified && (
              <p className="rounded-lg bg-purple-50 px-3 py-2 text-xs font-semibold text-purple-800">
                마케팅성 메일 · 사전심의필 번호 필요
              </p>
            )}
            {draft.failure_reason_code && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800">
                발송 실패 사유: {draft.failure_reason_code}
              </p>
            )}

            {canMutate && (
              <div className="flex flex-wrap gap-2">
                {draft.status_code === "DRAFT" && (
                  <button
                    type="button"
                    disabled={transition.isPending}
                    onClick={() => transition.mutate({ draftId: draft.draft_id, op: "submit" })}
                    className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
                  >
                    승인 요청
                  </button>
                )}
                {draft.status_code === "PENDING_APPROVAL" && (
                  <>
                    <button
                      type="button"
                      disabled={transition.isPending}
                      onClick={() => transition.mutate({ draftId: draft.draft_id, op: "approve" })}
                      className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      승인
                    </button>
                    <button
                      type="button"
                      disabled={transition.isPending}
                      onClick={() => {
                        const reason = window.prompt("반려 사유를 입력해 주세요. (감사 로그에 기록됩니다)", "");
                        if (reason && reason.trim()) {
                          transition.mutate({ draftId: draft.draft_id, op: "reject", reason: reason.trim() });
                        }
                      }}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                    >
                      반려 (초안으로 되돌리기)
                    </button>
                  </>
                )}
                {draft.status_code === "APPROVED" && (
                  <button
                    type="button"
                    disabled={transition.isPending}
                    onClick={() => transition.mutate({ draftId: draft.draft_id, op: "send" })}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    발송 (샌드박스)
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
