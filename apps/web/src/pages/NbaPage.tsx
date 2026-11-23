/**
 * NBA 인박스 — T243/T16/T17
 * P1/P2/P3 우선순위 카드, SLA 카운트다운, why_link 근거 링크, 조치 버튼,
 * Wave 1 티켓 플로우 클라이언트를 통한 WS 실시간 업데이트.
 */
import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StatusBadge } from "../components/Badges";
import { getResource, postResource } from "../lib/api";
import { actionTypeLabel, eventTypeLabel } from "../lib/labels";
import { connectHarnessWebSocket } from "../lib/websocket";
import { useAuthStore } from "../store/auth";
import type { ListResponse, WebSocketEvent } from "../lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NbaAction {
  id: string;
  customer_id?: string;
  customer_name?: string;
  action_type_code: string;
  priority_code: string;
  status_code: string;
  due_date?: string;
  created_at?: string;
  script_text?: string;
  script_disclosure?: string;
  why_link?: string;
  score?: number;
  sla_timer_seconds?: number;
  trigger_code?: string;
}

interface AftercareTask {
  id: string;
  customer_name?: string;
  event_type_code: string;
  status_code: string;
  due_date?: string;
  quarter_code?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function nbaPriorityTone(code: string): "red" | "orange" | "blue" | "gray" {
  if (code === "P1" || code === "URGENT") return "red";
  if (code === "P2" || code === "HIGH") return "orange";
  if (code === "P3" || code === "MEDIUM") return "blue";
  return "gray";
}

function nbaPriorityLabel(code: string): string {
  const MAP: Record<string, string> = {
    P1: "P1 긴급",
    P2: "P2 높음",
    P3: "P3 보통",
    URGENT: "긴급",
    HIGH: "높음",
    MEDIUM: "보통",
    LOW: "낮음",
  };
  return MAP[code] ?? code;
}

function effectiveDueDate(action: NbaAction): string | undefined {
  if (action.due_date) return action.due_date;
  if (action.sla_timer_seconds && action.created_at) {
    return new Date(
      new Date(action.created_at).getTime() + action.sla_timer_seconds * 1_000,
    ).toISOString();
  }
  return undefined;
}

function calcSlaRemaining(dueDate: string | undefined): string {
  if (!dueDate) return "기한 미설정";
  const diff = new Date(dueDate).getTime() - Date.now();
  if (diff <= 0) return "기한 초과";
  const totalMins = Math.floor(diff / 60_000);
  const hours = Math.floor(totalMins / 60);
  const mins = totalMins % 60;
  if (hours >= 24) return `${Math.floor(hours / 24)}일 ${hours % 24}시간 남음`;
  return `${hours}시간 ${mins}분 남음`;
}

function getCurrentQuarter(): string {
  const now = new Date();
  return `${now.getFullYear()}Q${Math.ceil((now.getMonth() + 1) / 3)}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SlaBadge({ dueDate }: { dueDate: string | undefined }) {
  const [label, setLabel] = useState(() => calcSlaRemaining(dueDate));

  useEffect(() => {
    if (!dueDate) return;
    setLabel(calcSlaRemaining(dueDate));
    const id = window.setInterval(() => setLabel(calcSlaRemaining(dueDate)), 30_000);
    return () => window.clearInterval(id);
  }, [dueDate]);

  const diff = dueDate ? new Date(dueDate).getTime() - Date.now() : Infinity;
  const isOverdue = diff <= 0;
  const isUrgent = !isOverdue && diff < 4 * 3_600_000;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold tabular-nums ${
        isOverdue
          ? "border-red-200 bg-red-50 text-red-700"
          : isUrgent
            ? "border-amber-200 bg-amber-50 text-amber-700"
            : "border-slate-200 bg-slate-50 text-slate-600"
      }`}
    >
      <svg className="size-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path strokeLinecap="round" d="M12 6v6l4 2" />
      </svg>
      {label}
    </span>
  );
}

function WsStatusDot({ status }: { status: "connecting" | "open" | "closed" | "failed" }) {
  const COLORS = { connecting: "bg-amber-400 animate-pulse", open: "bg-emerald-500", closed: "bg-slate-400", failed: "bg-red-500" };
  const LABELS = { connecting: "연결 중", open: "실시간", closed: "연결 끊김", failed: "연결 실패" };
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-500" role="status" aria-live="polite">
      <span className={`size-2 rounded-full ${COLORS[status]}`} aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}

function NbaCard({
  action,
  onAction,
  isPending,
  onGenerateScript,
  isGeneratingScript,
}: {
  action: NbaAction;
  onAction: (id: string, op: "acknowledge" | "complete" | "dismiss") => void;
  isPending: boolean;
  onGenerateScript: ((id: string) => void) | null;
  isGeneratingScript: boolean;
}) {
  const tone = nbaPriorityTone(action.priority_code);
  const borderLeft =
    tone === "red" ? "border-l-red-600" : tone === "orange" ? "border-l-amber-500" : tone === "blue" ? "border-l-blue-600" : "border-l-slate-300";
  const badgeCls =
    tone === "red"
      ? "border-red-200 bg-red-50 text-red-700"
      : tone === "orange"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : tone === "blue"
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : "border-slate-200 bg-slate-50 text-slate-600";

  const dueDate = effectiveDueDate(action);
  const canAcknowledge = action.status_code === "PENDING";
  const canAct = action.status_code === "PENDING" || action.status_code === "IN_PROGRESS";

  return (
    <article
      className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm border-l-4 ${borderLeft}`}
      aria-label={`NBA 카드: ${action.customer_name ?? action.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-bold text-slate-900 truncate">{action.customer_name ?? action.id}</p>
          <p className="mt-0.5 text-sm text-slate-500">
            {actionTypeLabel(action.action_type_code)}
            {action.trigger_code ? ` · ${eventTypeLabel(action.trigger_code)}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5 items-center">
          <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-bold ${badgeCls}`}>
            {nbaPriorityLabel(action.priority_code)}
          </span>
          <StatusBadge statusCode={action.status_code} />
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <SlaBadge dueDate={dueDate} />
        {action.score !== undefined && (
          <span className="text-xs text-slate-400 tabular-nums">스코어 {Number(action.score).toFixed(2)}</span>
        )}
        {action.why_link && (
          <a
            href={action.why_link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 text-xs font-semibold text-blue-700 hover:underline"
            aria-label="근거 문서 열기"
          >
            <svg className="size-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            근거 보기
          </a>
        )}
      </div>

      {action.script_text && (
        <details className="mt-3">
          <summary className="cursor-pointer select-none text-sm font-semibold text-blue-700">AI 스크립트 보기</summary>
          <p className="mt-2 rounded-xl bg-slate-50 p-3 text-sm leading-relaxed text-slate-600">{action.script_text}</p>
          {action.script_disclosure && (
            <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-700">
              {action.script_disclosure}
            </p>
          )}
        </details>
      )}

      {onGenerateScript && !action.script_text && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <button
            type="button"
            disabled={isGeneratingScript}
            onClick={() => onGenerateScript(action.id)}
            className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {isGeneratingScript ? "AI 스크립트 생성 중…" : "AI 스크립트 생성"}
          </button>
        </div>
      )}

      {canAct && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
          {canAcknowledge && (
            <button
              type="button"
              disabled={isPending}
              onClick={() => onAction(action.id, "acknowledge")}
              className="rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-800 disabled:opacity-50"
            >
              접수
            </button>
          )}
          <button
            type="button"
            disabled={isPending}
            onClick={() => onAction(action.id, "complete")}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            완료
          </button>
          <button
            type="button"
            disabled={isPending}
            onClick={() => onAction(action.id, "dismiss")}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            해제
          </button>
        </div>
      )}
    </article>
  );
}

function AftercareWidget() {
  const quarter = getCurrentQuarter();
  const tasks = useQuery({
    queryKey: ["aftercare-quarterly", quarter],
    queryFn: () =>
      getResource<{ quarter: string; items: AftercareTask[]; count: number }>(
        `/aftercare/quarterly?quarter=${quarter}`,
      ),
  });
  const items = tasks.data?.items ?? [];

  return (
    <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-slate-900">사후관리 대기</h2>
          <p className="text-xs text-slate-500">{quarter} 분기 · T244</p>
        </div>
        {tasks.data && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700">
            {tasks.data.count}건
          </span>
        )}
      </div>
      {tasks.isLoading && <p className="text-sm text-slate-400">불러오는 중…</p>}
      {tasks.error && <p className="text-sm text-amber-700">사후관리 데이터 조회 실패</p>}
      <div className="grid gap-2">
        {items.slice(0, 6).map((task) => {
          const dueDate = task.due_date;
          return (
            <div key={task.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-800">{task.customer_name ?? task.id}</p>
                <p className="text-xs text-slate-500">{eventTypeLabel(task.event_type_code)}</p>
              </div>
              <SlaBadge dueDate={dueDate} />
            </div>
          );
        })}
        {items.length === 0 && !tasks.isLoading && (
          <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">
            이번 분기 대기 중인 사후관리가 없습니다.
          </p>
        )}
        {items.length > 6 && (
          <p className="text-xs text-slate-400">외 {items.length - 6}건 더 있음</p>
        )}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type TabKey = "pending" | "in_progress";

export function NbaPage() {
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed" | "failed">("connecting");
  const [tab, setTab] = useState<TabKey>("pending");
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.roleCode === "ADMIN";

  const statusParam = tab === "pending" ? "PENDING" : "IN_PROGRESS";
  const actions = useQuery({
    queryKey: ["nba-actions", statusParam],
    queryFn: () =>
      getResource<ListResponse<NbaAction>>(`/nba-actions?status_code=${statusParam}&limit=50`),
  });
  const items = actions.data?.items ?? [];

  const actionMutation = useMutation({
    mutationFn: ({ id, op }: { id: string; op: "acknowledge" | "complete" | "dismiss" }) =>
      postResource<NbaAction>(`/nba-cards/${id}/${op}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["nba-actions"] }),
  });

  const handleAction = useCallback(
    (id: string, op: "acknowledge" | "complete" | "dismiss") => {
      actionMutation.mutate({ id, op });
    },
    [actionMutation],
  );

  const generateScriptMutation = useMutation({
    mutationFn: (id: string) =>
      postResource<NbaAction>(
        `/nba-cards/${id}/generate-script`,
        undefined,
        { idempotencyKey: crypto.randomUUID() },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["nba-actions"] }),
  });

  const handleGenerateScript = useCallback(
    (id: string) => generateScriptMutation.mutate(id),
    [generateScriptMutation],
  );

  // WS realtime: invalidate on nba_created / nba_updated
  useEffect(() => {
    const cleanup = connectHarnessWebSocket({
      getToken: () => accessToken,
      onEvent: (event: WebSocketEvent) => {
        if (event.event_type === "nba_created" || event.event_type === "nba_updated") {
          void queryClient.invalidateQueries({ queryKey: ["nba-actions"] });
        }
      },
      onStatusChange: setWsStatus,
    });
    return cleanup;
  }, [accessToken, queryClient]);

  const TABS: Array<{ key: TabKey; label: string }> = [
    { key: "pending", label: "대기" },
    { key: "in_progress", label: "진행 중" },
  ];

  return (
    <div className="grid gap-6">
      {/* NBA 인박스 카드 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-black text-slate-950">NBA 인박스</h1>
            <p className="mt-0.5 text-sm text-slate-500">우선순위 기반 후속 조치 관리함</p>
          </div>
          <WsStatusDot status={wsStatus} />
        </div>

        {/* Priority legend */}
        <div className="mt-3 flex flex-wrap gap-3 text-xs">
          {(["P1", "P2", "P3"] as const).map((p) => {
            const tone = nbaPriorityTone(p);
            const cls =
              tone === "red"
                ? "border-red-600 bg-red-50 text-red-700"
                : tone === "orange"
                  ? "border-amber-500 bg-amber-50 text-amber-700"
                  : "border-blue-600 bg-blue-50 text-blue-700";
            return (
              <span key={p} className={`rounded border-l-2 px-2 py-0.5 font-semibold ${cls}`}>
                {nbaPriorityLabel(p)}
              </span>
            );
          })}
        </div>

        {/* Tabs */}
        <div className="mt-4 flex gap-1 rounded-xl bg-slate-100 p-1" role="tablist">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              type="button"
              onClick={() => setTab(key)}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                tab === key ? "bg-white text-slate-950 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Card list */}
        <div className="mt-4 grid gap-3" role="tabpanel">
          {actions.isLoading && (
            <p className="py-4 text-center text-sm text-slate-400">불러오는 중…</p>
          )}
          {actions.error && (
            <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
              데이터를 불러오지 못했습니다.
            </p>
          )}
          {actionMutation.error && (
            <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">
              처리 중 오류가 발생했습니다.
            </p>
          )}
          {!actions.isLoading && items.length === 0 && (
            <p className="rounded-xl bg-slate-50 p-5 text-center text-sm text-slate-500">
              {tab === "pending" ? "대기 중인 NBA 카드가 없습니다." : "진행 중인 NBA 카드가 없습니다."}
            </p>
          )}
          {items.map((action) => (
            <NbaCard
              key={action.id}
              action={action}
              onAction={handleAction}
              isPending={actionMutation.isPending}
              onGenerateScript={isAdmin ? handleGenerateScript : null}
              isGeneratingScript={generateScriptMutation.isPending}
            />
          ))}
        </div>
      </section>

      {/* Aftercare quarterly widget */}
      <AftercareWidget />
    </div>
  );
}
