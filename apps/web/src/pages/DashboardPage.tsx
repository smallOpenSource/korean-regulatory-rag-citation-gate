import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiPanel } from "../components/ApiPanel";
import { AiGeneratedBadge, PriorityBadge, StatusBadge } from "../components/Badges";
import { getResource } from "../lib/api";
import { formatBankerNumber, formatBankerTimestamp } from "../lib/format";
import { sourceLabel } from "../lib/labels";
import type { DomesticMarketStatus, DomesticTop200Coverage, SyntheticCustomerNotice } from "../lib/types";

interface DashboardPayload {
  urgent_nba_count?: number;
  due_maturity_count?: number;
  consultations_today?: number;
  latest_house_view?: {
    summary?: string;
    ai_generated_at?: string;
    ai_model_name?: string;
    // P2-6: AI-body data-quality signals attached by the dashboard router
    data_quality_notice?: string;
    faithfulness?: { passed?: boolean; flags?: string[]; ungrounded_figures?: string[] };
  };
  domestic_market_status?: DomesticMarketStatus;
  synthetic_customer_notice?: SyntheticCustomerNotice;
}

export function DashboardPage() {
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: () => getResource<DashboardPayload>("/dashboard") });

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-blue-700 to-slate-900 p-8 text-white shadow-sm">
        <p className="text-sm font-bold uppercase tracking-[0.3em] text-blue-100">대시보드</p>
        <h1 className="mt-3 text-3xl font-black">PB/WM 오늘의 업무 우선순위</h1>
        <p className="mt-3 max-w-3xl text-blue-50">긴급 후속 조치, 만기 임박, 상담 일정, 최신 하우스뷰를 한 화면에서 확인합니다.</p>
      </section>
      {dashboard.data?.synthetic_customer_notice ? (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge statusCode={dashboard.data.synthetic_customer_notice.status_code} />
            <p className="font-semibold">{dashboard.data.synthetic_customer_notice.message}</p>
          </div>
        </section>
      ) : null}
      <ApiPanel title="업무 지표" error={dashboard.error}>
        <div className="grid gap-4 md:grid-cols-3">
          <Metric
            label="긴급 후속 조치"
            display={` ${formatBankerNumber(dashboard.data?.urgent_nba_count ?? 0, "건")}`}
            badge={<PriorityBadge priorityCode="URGENT" />}
          />
          <Metric label="7일 이내 만기" display={` ${formatBankerNumber(dashboard.data?.due_maturity_count ?? 0, "건")}`} />
          <Metric label="오늘 상담" display={` ${formatBankerNumber(dashboard.data?.consultations_today ?? 0, "건")}`} />
        </div>
      </ApiPanel>
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">국내 시장 데이터 상태</h2>
            <p className="mt-2 text-sm text-slate-600">
              {dashboard.data?.domestic_market_status?.message ?? "국내 시장 데이터 준비 상태를 불러오는 중입니다."}
            </p>
          </div>
          <StatusBadge statusCode={dashboard.data?.domestic_market_status?.status_code ?? "LOADING"} />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <MarketFact label="출처" value={sourceLabel(dashboard.data?.domestic_market_status?.source_code)} />
          <MarketFact label="기준시각" value={formatBankerTimestamp(dashboard.data?.domestic_market_status?.source_as_of)} />
          <MarketFact label="신선도" value={<StatusBadge statusCode={dashboard.data?.domestic_market_status?.freshness_status_code ?? "MISSING"} />} />
          <MarketFact label="품질" value={<StatusBadge statusCode={dashboard.data?.domestic_market_status?.quality_status_code ?? "UNVERIFIED"} />} />
        </div>
        <Top200CoverageSummary coverage={dashboard.data?.domestic_market_status?.top200_coverage} />
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">최신 하우스뷰 요약</h2>
            <p className="mt-2 text-sm text-slate-600">
              {dashboard.data?.latest_house_view?.summary
                ?? (dashboard.isPending ? "최신 하우스뷰 요약을 불러오는 중입니다." : "활성 하우스뷰가 등록되지 않았습니다.")}
            </p>
          </div>
          <AiGeneratedBadge
            generatedAt={dashboard.data?.latest_house_view?.ai_generated_at}
            modelName={dashboard.data?.latest_house_view?.ai_model_name}
          />
        </div>
        {dashboard.data?.latest_house_view?.data_quality_notice && (
          <div
            className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
            role="note"
            data-testid="dashboard-house-view-data-quality-notice"
          >
            <span className="font-bold">데이터 품질 고지: </span>
            <span>{dashboard.data.latest_house_view.data_quality_notice}</span>
          </div>
        )}
        {dashboard.data?.latest_house_view?.faithfulness && (
          <div
            className="mt-2 flex flex-wrap items-center gap-1.5 text-xs"
            data-testid="dashboard-house-view-faithfulness"
          >
            <span
              className={`rounded-full px-2 py-0.5 font-bold ${
                dashboard.data.latest_house_view.faithfulness.passed
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-amber-100 text-amber-800"
              }`}
            >
              근거충실성:{" "}
              {dashboard.data.latest_house_view.faithfulness.passed ? "확인" : "검토 필요"}
            </span>
          </div>
        )}
      </section>
    </div>
  );
}

function Metric({ label, display, badge }: { label: string; display: string; badge?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        {badge}
      </div>
      <p className="mt-3 text-3xl font-black text-slate-950">{display}</p>
    </div>
  );
}

function MarketFact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <div className="mt-2 text-sm font-bold text-slate-900">{value}</div>
    </div>
  );
}

function formatInteger(value?: number | null): string {
  // Wave-Audit-Defect-Fix Wave D per-page: delegate to canonical helper.
  return formatBankerNumber(typeof value === "number" ? value : null);
}

function formatPercent(value?: number | null): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "수치 미확정";
}

function Top200CoverageSummary({ coverage }: { coverage?: DomesticTop200Coverage }) {
  if (!coverage) {
    return null;
  }
  // When the profile intentionally skips the top-200 gate (PoC default) and
  // no snapshot has been captured, suppress the entire card so PB users do
  // not see a "차단 / 0% / 차단 사유 …" panel for a gate that does not apply.
  if (coverage.required === false && (coverage.snapshot_count ?? 0) === 0) {
    return null;
  }

  return (
    <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-900">상위 200개 공식 KRX 커버리지</p>
          <p className="mt-1 text-sm text-slate-600">
            선택 {formatInteger(coverage.selected_count)}개 · 최근 {formatInteger(coverage.lookback_days)}일 ·
            커버리지 {formatPercent(coverage.coverage_ratio)}
          </p>
        </div>
        <StatusBadge statusCode={coverage.status_code} />
      </div>
      <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-3">
        <span>종목-거래일 {formatInteger(coverage.observed_member_days)} / {formatInteger(coverage.expected_member_days)}</span>
        <span>누락 {formatInteger(coverage.missing_member_days)}</span>
        <span>KRX 기준시각 {formatBankerTimestamp(coverage.latest_source_as_of)}</span>
      </div>
      {(coverage.blocking_reasons ?? []).length ? (
        <p className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
          차단 사유: {(coverage.blocking_reasons ?? []).join(" / ")}
        </p>
      ) : null}
    </div>
  );
}
