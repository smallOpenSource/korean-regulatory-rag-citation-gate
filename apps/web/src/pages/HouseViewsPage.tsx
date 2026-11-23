/**
 * HouseViewsPage — house view list with PB-utility controls (T29).
 *
 * Stage 2 expansion from 33 LOC stub: filter by status (server-side query),
 * client-side title search + period_code facet, sort toggle, ADMIN-only
 * create-draft form. List items still link to HouseViewDetailPage for the
 * lifecycle view; this page is the discovery surface above the detail page.
 *
 * Browser verification: deferred to next /compact (UI smoke test against
 * dev server + role × status combinations).
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiPanel } from "../components/ApiPanel";
import { AiGeneratedBadge, StatusBadge } from "../components/Badges";
import { getResource, postResource } from "../lib/api";
import { useAuthStore } from "../store/auth";
import type { ListResponse } from "../lib/types";

interface HouseView {
  id: string;
  version_no: number;
  period_code: string;
  title: string;
  status_code: string;
  summary?: string;
  ai_generated_at?: string;
  ai_model_name?: string;
}

// Status filter chips — must match status_code values produced by the
// repository LIST query (excluding QA-fixture statuses that the server
// already filters out of the default response).
const STATUS_CHIPS: { code: string; label: string }[] = [
  { code: "", label: "전체" },
  { code: "DRAFT", label: "초안" },
  { code: "GENERATED", label: "생성됨" },
  { code: "REVIEWED", label: "검토" },
  { code: "ACTIVE", label: "활성" },
  { code: "ARCHIVED", label: "보관" },
  { code: "SUPERSEDED", label: "이전 버전" },
];

type SortKey = "version_desc" | "version_asc" | "generated_desc";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "version_desc", label: "버전 ↓" },
  { value: "version_asc", label: "버전 ↑" },
  { value: "generated_desc", label: "최근 생성 ↓" },
];

function applyClientFilters(
  items: HouseView[],
  search: string,
  periodFilter: string,
  sortKey: SortKey,
): HouseView[] {
  const needle = search.trim().toLowerCase();
  const filtered = items.filter((view) => {
    if (needle && !view.title.toLowerCase().includes(needle)) {
      return false;
    }
    if (periodFilter && view.period_code !== periodFilter) {
      return false;
    }
    return true;
  });

  const sorted = [...filtered];
  sorted.sort((a, b) => {
    if (sortKey === "version_desc") return b.version_no - a.version_no;
    if (sortKey === "version_asc") return a.version_no - b.version_no;
    // generated_desc — unknown ai_generated_at sinks to the end
    const aT = a.ai_generated_at ?? "";
    const bT = b.ai_generated_at ?? "";
    if (!aT && !bT) return 0;
    if (!aT) return 1;
    if (!bT) return -1;
    return bT.localeCompare(aT);
  });
  return sorted;
}

function CreateDraftForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [periodCode, setPeriodCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (payload: { title: string; period_code: string }) =>
      // ADR-011: POST /house-views is @idempotent; supply per-click UUID
      // so retries replay rather than duplicate-create the house view.
      postResource<HouseView>("/house-views", payload, {
        idempotencyKey: crypto.randomUUID(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["house-views"] });
      setTitle("");
      setPeriodCode("");
      setError(null);
      onCreated();
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : "초안 생성에 실패했습니다.";
      setError(message);
    },
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const trimmedPeriod = periodCode.trim() || "MVP";
    if (!trimmedTitle) {
      setError("타이틀을 입력하세요.");
      return;
    }
    createMutation.mutate({ title: trimmedTitle, period_code: trimmedPeriod });
  };

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-blue-200 bg-blue-50 p-4"
      aria-label="새 하우스뷰 초안 생성"
    >
      <p className="mb-3 text-xs font-bold uppercase tracking-wider text-blue-700">
        ADMIN · 새 하우스뷰 초안
      </p>
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr_auto]">
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          타이틀
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="예: 2026 Q3 자산배분 하우스뷰"
            disabled={createMutation.isPending}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          기간 코드
          <input
            type="text"
            value={periodCode}
            onChange={(e) => setPeriodCode(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="예: 2026Q3"
            disabled={createMutation.isPending}
          />
        </label>
        <button
          type="submit"
          className="self-end rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          disabled={createMutation.isPending}
        >
          {createMutation.isPending ? "생성 중…" : "초안 생성"}
        </button>
      </div>
      {error ? (
        <p className="mt-2 text-xs text-red-700" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

export function HouseViewsPage() {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [periodFilter, setPeriodFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("version_desc");
  const role = useAuthStore((s) => s.user?.roleCode);
  const isAdmin = role === "ADMIN";

  const houseViews = useQuery({
    queryKey: ["house-views", statusFilter],
    queryFn: () => {
      const query = statusFilter ? `?status_code=${encodeURIComponent(statusFilter)}` : "";
      return getResource<ListResponse<HouseView>>(`/house-views${query}`);
    },
  });

  const rawItems = houseViews.data?.items ?? [];

  const periodOptions = useMemo(() => {
    const set = new Set<string>();
    rawItems.forEach((view) => {
      if (view.period_code) set.add(view.period_code);
    });
    return Array.from(set).sort();
  }, [rawItems]);

  const visibleItems = useMemo(
    () => applyClientFilters(rawItems, search, periodFilter, sortKey),
    [rawItems, search, periodFilter, sortKey],
  );

  return (
    <ApiPanel title="하우스뷰 목록" error={houseViews.error}>
      <div className="grid gap-4">
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <strong className="font-bold">합성 데이터</strong> · 본 화면의 하우스뷰는 합성 시나리오 기반이며,
          실제 운용 결정의 직접적 근거가 아닙니다.
        </div>

        {isAdmin ? <CreateDraftForm onCreated={() => setStatusFilter("DRAFT")} /> : null}

        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="상태 필터">
          {STATUS_CHIPS.map((chip) => {
            const active = chip.code === statusFilter;
            return (
              <button
                key={chip.code || "all"}
                type="button"
                onClick={() => setStatusFilter(chip.code)}
                className={
                  active
                    ? "rounded-full border border-blue-700 bg-blue-700 px-3 py-1 text-xs font-semibold text-white"
                    : "rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-700 hover:border-slate-500"
                }
                aria-pressed={active}
              >
                {chip.label}
              </button>
            );
          })}
        </div>

        <div className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_auto]">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="타이틀 검색"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            aria-label="타이틀 검색"
          />
          <select
            value={periodFilter}
            onChange={(e) => setPeriodFilter(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            aria-label="기간 코드 필터"
          >
            <option value="">전체 기간</option>
            {periodOptions.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            aria-label="정렬 기준"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <span className="self-center rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
            총 {visibleItems.length}건 {rawItems.length !== visibleItems.length ? `(전체 ${rawItems.length})` : ""}
          </span>
        </div>

        {houseViews.isPending ? (
          <p className="text-sm text-slate-500">불러오는 중…</p>
        ) : visibleItems.length === 0 ? (
          <p className="text-sm text-slate-500">
            {rawItems.length === 0
              ? "하우스뷰 이력이 없습니다."
              : "필터 조건에 맞는 하우스뷰가 없습니다."}
          </p>
        ) : (
          visibleItems.map((view) => (
            <article className="rounded-2xl border border-slate-200 p-4" key={view.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Link className="text-lg font-black text-blue-700" to={`/house-views/${view.id}`}>
                    {view.title}
                  </Link>
                  <p className="text-sm text-slate-600">
                    v{view.version_no} · {view.period_code}
                  </p>
                </div>
                <span className="flex gap-2">
                  <StatusBadge statusCode={view.status_code} />
                  <AiGeneratedBadge generatedAt={view.ai_generated_at} modelName={view.ai_model_name} />
                </span>
              </div>
              <p className="mt-3 text-sm text-slate-600">{view.summary ?? "요약이 아직 생성되지 않았습니다."}</p>
            </article>
          ))
        )}
      </div>
    </ApiPanel>
  );
}
