/**
 * 후속 조치 (분기 사후관리 큐 — T244/T257)
 *
 * Quarterly aftercare queue: due-soon, in-flight, completed events for the actor's customers.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getResource, postResource } from "../lib/api";
import { eventTypeLabel } from "../lib/labels";
import { useAuthStore } from "../store/auth";

type AftercareStatus =
  | "PENDING"
  | "OPEN"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "RESOLVED"
  | "SKIPPED";

// Backend uses OPEN/IN_PROGRESS/RESOLVED for legacy events, plus PENDING/COMPLETED/SKIPPED
// for the quarterly lifecycle. The UI shows four buckets — collapse equivalents below.
const STATUS_TO_BUCKET: Record<AftercareStatus, "PENDING" | "IN_PROGRESS" | "COMPLETED" | "SKIPPED"> = {
  PENDING: "PENDING",
  OPEN: "PENDING",
  IN_PROGRESS: "IN_PROGRESS",
  COMPLETED: "COMPLETED",
  RESOLVED: "COMPLETED",
  SKIPPED: "SKIPPED",
};

interface AftercareTask {
  id: string;
  customer_id: string;
  customer_name?: string;
  event_type_code: string;
  status_code: AftercareStatus;
  due_date?: string;
  scheduled_quarter?: string;
}

interface QuarterlyResponse {
  quarter: string;
  items: AftercareTask[];
  count: number;
}

function getCurrentQuarter(): string {
  const now = new Date();
  const year = now.getFullYear();
  const quarter = Math.ceil((now.getMonth() + 1) / 3);
  return `${year}Q${quarter}`;
}

function quarterOptions(current: string): string[] {
  const match = /^(\d{4})Q([1-4])$/.exec(current);
  if (!match) return [current];
  const year = Number(match[1]);
  const q = Number(match[2]);
  const list: string[] = [];
  for (const offset of [-1, 0, 1]) {
    let yy = year;
    let qq = q + offset;
    while (qq < 1) {
      qq += 4;
      yy -= 1;
    }
    while (qq > 4) {
      qq -= 4;
      yy += 1;
    }
    list.push(`${yy}Q${qq}`);
  }
  return list;
}

function StatusBadge({ statusCode }: { statusCode: AftercareTask["status_code"] }) {
  const palette: Record<AftercareTask["status_code"], string> = {
    PENDING: "bg-amber-100 text-amber-800",
    OPEN: "bg-amber-100 text-amber-800",
    IN_PROGRESS: "bg-blue-100 text-blue-800",
    COMPLETED: "bg-emerald-100 text-emerald-800",
    RESOLVED: "bg-emerald-100 text-emerald-800",
    SKIPPED: "bg-slate-100 text-slate-600",
  };
  const label: Record<AftercareTask["status_code"], string> = {
    PENDING: "대기",
    OPEN: "진행 필요",
    IN_PROGRESS: "진행",
    COMPLETED: "완료",
    RESOLVED: "해결",
    SKIPPED: "보류",
  };
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${palette[statusCode]}`}>
      {label[statusCode]}
    </span>
  );
}

function formatDueDate(value?: string): string {
  // Wave-Audit-Defect-Fix Wave D per-page: legacy banned-pattern fallback
  // replaced with the canonical 미확정 suffix per PB-perspective ban.
  if (!value) return "기한 미확정";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function AftercarePage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [quarter, setQuarter] = useState<string>(getCurrentQuarter());
  const canMutate = user?.roleCode === "PB" || user?.roleCode === "WM";

  const tasks = useQuery({
    queryKey: ["aftercare-quarterly", quarter],
    queryFn: () => getResource<QuarterlyResponse>(`/aftercare/quarterly?quarter=${quarter}`),
  });

  const resolveMutation = useMutation({
    mutationFn: ({ id, op }: { id: string; op: "resolve" | "complete" | "skip" }) =>
      postResource<unknown>(`/aftercare-events/${id}/${op}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["aftercare-quarterly"] }),
  });

  const items = tasks.data?.items ?? [];
  const groups = useMemo(() => {
    const buckets: Record<"PENDING" | "IN_PROGRESS" | "COMPLETED" | "SKIPPED", AftercareTask[]> = {
      PENDING: [],
      IN_PROGRESS: [],
      COMPLETED: [],
      SKIPPED: [],
    };
    for (const item of items) {
      const key = STATUS_TO_BUCKET[item.status_code] ?? "PENDING";
      buckets[key].push(item);
    }
    return buckets;
  }, [items]);

  const quarters = quarterOptions(quarter);

  return (
    <section className="grid gap-6">
      <header className="rounded-3xl bg-gradient-to-br from-blue-700 via-blue-600 to-cyan-600 p-7 text-white shadow-md">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-100">사후관리 분기 큐</p>
        <h1 className="mt-2 text-2xl font-black">후속 조치</h1>
        <p className="mt-3 max-w-3xl text-blue-50">
          분기별 사후관리 대상 고객을 한 화면에서 확인하고, 처리 상태를 업데이트합니다.
          담당 고객 범위 안의 항목만 표시됩니다.
        </p>
      </header>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong className="font-bold">합성 데이터</strong> · 고객·계좌·후속 조치는 모두 합성 데이터입니다. 실제 고객 식별자로 해석하지 마세요.
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="aftercare-quarter" className="text-sm font-semibold text-slate-700">
          기준 분기
        </label>
        <select
          id="aftercare-quarter"
          value={quarter}
          onChange={(event) => setQuarter(event.target.value)}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-800 shadow-sm"
        >
          {quarters.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-700">
          총 {tasks.data?.count ?? 0}건
        </span>
      </div>

      {tasks.isLoading && <p className="text-sm text-slate-500">정보를 불러오는 중입니다.</p>}
      {tasks.error && (
        <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          사후관리 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {(["PENDING", "IN_PROGRESS", "COMPLETED", "SKIPPED"] as const).map((bucket) => (
          <article key={bucket} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-bold text-slate-900">
                {bucket === "PENDING" && "진행 필요"}
                {bucket === "IN_PROGRESS" && "진행 중"}
                {bucket === "COMPLETED" && "완료"}
                {bucket === "SKIPPED" && "보류"}
              </h2>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700">
                {groups[bucket].length}건
              </span>
            </div>
            <ul className="grid gap-2">
              {groups[bucket].length === 0 && (
                <li className="rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-500">
                  해당 항목이 없습니다.
                </li>
              )}
              {groups[bucket].map((task) => (
                <li
                  key={task.id}
                  className="grid gap-1.5 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-slate-800">
                      {task.customer_name ?? task.customer_id}
                    </p>
                    <StatusBadge statusCode={task.status_code} />
                  </div>
                  <p className="text-xs text-slate-500">
                    유형 {eventTypeLabel(task.event_type_code)} · 기한 {formatDueDate(task.due_date)}
                  </p>
                  {canMutate && bucket === "PENDING" && (
                    <div className="mt-1 flex gap-2">
                      <button
                        type="button"
                        disabled={resolveMutation.isPending}
                        onClick={() => resolveMutation.mutate({ id: task.id, op: "resolve" })}
                        className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        진행 시작
                      </button>
                      <button
                        type="button"
                        disabled={resolveMutation.isPending}
                        onClick={() => resolveMutation.mutate({ id: task.id, op: "skip" })}
                        className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                      >
                        다음 분기로 미루기
                      </button>
                    </div>
                  )}
                  {canMutate && bucket === "IN_PROGRESS" && (
                    <div className="mt-1 flex gap-2">
                      <button
                        type="button"
                        disabled={resolveMutation.isPending}
                        onClick={() => resolveMutation.mutate({ id: task.id, op: "complete" })}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                      >
                        완료 처리
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
