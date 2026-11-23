/**
 * Customer360Page — Wave 4 update (REG-03 T240 / T255)
 *
 * Adds a tab navigation system with four tabs:
 *   개요      — existing customer summary + AI briefing
 *   포트폴리오 — existing portfolio holdings
 *   후속 조치  — existing NBA actions + aftercare events
 *   가족 관계  — new HouseholdTab (synthetic data, T240)
 *
 * AIMetadataFooter added to the AI briefing card (T255).
 * Synthetic watermark displayed whenever payload.synthetic_customer_notice exists.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ApiPanel } from "../components/ApiPanel";
import { AiGeneratedBadge, PriorityBadge, StatusBadge } from "../components/Badges";
import { AIMetadataFooter } from "../components/AIMetadataFooter";
import { HouseholdTab } from "../components/HouseholdTab";
import { getResource, postResource } from "../lib/api";
import { formatBankerTimestamp, formatKRW } from "../lib/format";
import {
  actionTypeLabel,
  eventTypeLabel,
  riskGradeLabel,
  segmentLabel,
  sourceLabel,
  statusLabel,
} from "../lib/labels";
import { KO } from "../lib/i18n";
import type { SyntheticCustomerNotice, ValuationSource } from "../lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CustomerRow {
  id: string;
  customer_no?: string;
  customer_name?: string;
  scenario_label?: string;
  segment_code?: string;
  risk_grade_code?: string;
  total_assets_krw?: number | string;
}

interface CustomerDetail {
  customer?: CustomerRow;
  portfolios?: Array<{ id: string; portfolio_name?: string; valuation_date?: string }>;
  holdings?: Array<{
    id: string;
    portfolio_id?: string;
    product_name?: string;
    product_type_code?: string;
    market_value_krw?: number;
    weight_pct?: number | string;
    quantity?: number | string;
    as_of_date?: string;
    valuation_source?: ValuationSource;
  }>;
  portfolio_valuation?: ValuationSource & {
    portfolio_count?: number;
    holding_count?: number;
    display_basis_code?: string;
    total_market_value_krw?: number;
  };
  synthetic_customer_notice?: SyntheticCustomerNotice;
  ai_briefing?: {
    generated_at: string;
    model_name: string;
    summary: string;
    /** ai_outputs row ID for the AIMetadataFooter (T255) */
    output_id?: string;
  };
  nba_actions?: Array<{ id: string; priority_code: string; action_type_code: string; status_code: string }>;
  aftercare_events?: Array<{ id: string; event_type_code: string; status_code: string }>;
}

type TabId = "overview" | "portfolio" | "actions" | "household";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatKrw(value?: number | string | null): string {
  return formatKRW(value);
}

// Wave-Audit-Defect-Fix Wave D per-page: raw per-page number formatting was
// replaced with a module-scope Intl.NumberFormat to keep the canonical
// page-level-consistency-grep clean. Percentage with up to 2 fraction digits.
const PERCENT_FORMATTER = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });

function formatWeight(value?: number | string | null): string {
  if (value === undefined || value === null || value === "") return "";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "";
  return `${PERCENT_FORMATTER.format(n)}%`;
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <p className="mt-2 text-lg font-black">{value}</p>
    </div>
  );
}

// ─── Tab navigation ───────────────────────────────────────────────────────────

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview",   label: KO.customer360.overview },
  { id: "portfolio",  label: KO.customer360.portfolio },
  { id: "actions",    label: KO.customer360.actions },
  { id: "household",  label: KO.customer360.household },
];

function TabBar({ active, onChange }: { active: TabId; onChange: (t: TabId) => void }) {
  return (
    <nav
      className="flex gap-1 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm"
      role="tablist"
      aria-label="Customer 360 탭"
    >
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          aria-controls={`tab-panel-${tab.id}`}
          onClick={() => onChange(tab.id)}
          className={`flex-1 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
            active === tab.id
              ? "bg-blue-700 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

// ─── Tab panels ───────────────────────────────────────────────────────────────

function OverviewTab({
  detail,
  customerId,
}: {
  detail: CustomerDetail | undefined;
  customerId: string;
}) {
  const customer = detail?.customer;

  return (
    <div className="grid gap-6">
      {/* AI briefing panel */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">AI 브리핑 패널</h2>
            <p className="mt-2 text-sm text-slate-600">
              {detail?.ai_briefing?.summary ?? "상담 브리핑 생성 결과가 여기에 표시됩니다."}
            </p>
          </div>
          <AiGeneratedBadge
            generatedAt={detail?.ai_briefing?.generated_at}
            modelName={detail?.ai_briefing?.model_name}
          />
        </div>

        {/* T255: AI metadata 4-tuple footer */}
        {detail?.ai_briefing?.output_id ? (
          <AIMetadataFooter ai_output_id={detail.ai_briefing.output_id} />
        ) : null}

        <button
          type="button"
          onClick={() => void postResource(`/customers/${customerId}/portfolio-analysis`)}
          className="mt-4 rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white"
        >
          포트폴리오 분석 실행
        </button>
      </section>

      {/* Quick stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Info label="고객" value={customer?.customer_name ?? customer?.customer_no ?? customer?.id ?? customerId} />
        <Info label="세그먼트" value={segmentLabel(customer?.segment_code)} />
        <Info label="위험등급" value={riskGradeLabel(customer?.risk_grade_code)} />
        <Info label="총자산" value={formatKrw(customer?.total_assets_krw)} />
      </div>
      {customer?.scenario_label && (
        <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">
          <span className="font-semibold text-slate-700">시나리오</span>
          <span className="mx-1.5 text-slate-300">·</span>
          {customer.scenario_label}
        </div>
      )}

      {/* Consultation link */}
      <Link
        to={`/consultations/new?customerId=${customerId}`}
        className="flex items-center justify-center rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-700 hover:bg-blue-100"
      >
        상담 워크스페이스로 이동 →
      </Link>
    </div>
  );
}

function PortfolioTab({ detail }: { detail: CustomerDetail | undefined }) {
  return (
    <div className="grid gap-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">포트폴리오</h2>
            <p className="mt-2 text-sm text-slate-600">
              {detail?.portfolio_valuation?.message ?? "포트폴리오 평가 상태를 불러오는 중입니다."}
            </p>
          </div>
          <StatusBadge statusCode={detail?.portfolio_valuation?.status_code ?? "LOADING"} />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <Info label="평가 기준" value={statusLabel(detail?.portfolio_valuation?.display_basis_code)} />
          <Info label="출처" value={sourceLabel(detail?.portfolio_valuation?.source_code)} />
          <Info label="기준시각" value={formatBankerTimestamp(detail?.portfolio_valuation?.source_as_of)} />
          <Info label="품질" value={statusLabel(detail?.portfolio_valuation?.quality_status_code)} />
        </div>
        <div className="mt-4 grid gap-4">
          {(detail?.portfolios ?? []).map((portfolio) => (
            <article className="rounded-2xl bg-slate-50 p-4" key={portfolio.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-bold text-slate-900">
                  {portfolio.portfolio_name ?? "이름 없는 포트폴리오"}
                </h3>
                <p className="text-xs font-semibold text-slate-500">
                  기준일 {portfolio.valuation_date ?? ""}
                </p>
              </div>
              <div className="mt-3 grid gap-2">
                {(detail?.holdings ?? [])
                  .filter((h) => h.portfolio_id === portfolio.id)
                  .map((holding) => (
                    <div
                      className="grid gap-2 rounded-xl bg-white p-3 text-sm md:grid-cols-[1fr_8rem_7rem_16rem]"
                      key={holding.id}
                    >
                      <span className="font-semibold">{holding.product_name ?? "상품명 미확인"}</span>
                      <span className="text-slate-600">{formatKrw(holding.market_value_krw)}</span>
                      <span className="text-slate-600">비중 {formatWeight(holding.weight_pct)}</span>
                      <span className="text-xs text-slate-600">
                        출처 {sourceLabel(holding.valuation_source?.source_code)} ·
                        기준시각 {formatBankerTimestamp(holding.valuation_source?.source_as_of)} ·{" "}
                        {statusLabel(holding.valuation_source?.freshness_status_code)}
                      </span>
                    </div>
                  ))}
              </div>
            </article>
          ))}
          {(detail?.portfolios ?? []).length === 0 && (
            <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
              표시할 포트폴리오가 없습니다.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function ActionsTab({
  detail,
  customerId,
}: {
  detail: CustomerDetail | undefined;
  customerId: string;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold">진행 중인 후속 조치 / 사후관리</h2>
      <div className="grid gap-3">
        {(detail?.nba_actions ?? []).map((action) => (
          <div
            className="flex items-center justify-between rounded-xl bg-slate-50 p-3"
            key={action.id}
          >
            <span className="text-sm font-semibold">{actionTypeLabel(action.action_type_code)}</span>
            <span className="flex gap-2">
              <PriorityBadge priorityCode={action.priority_code} />
              <StatusBadge statusCode={action.status_code} />
            </span>
          </div>
        ))}
        {(detail?.aftercare_events ?? []).map((event) => (
          <div
            className="flex items-center justify-between rounded-xl bg-slate-50 p-3"
            key={event.id}
          >
            <span className="text-sm font-semibold">{eventTypeLabel(event.event_type_code)}</span>
            <StatusBadge statusCode={event.status_code} />
          </div>
        ))}
        {(detail?.nba_actions ?? []).length === 0 && (detail?.aftercare_events ?? []).length === 0 && (
          <p className="text-sm text-slate-500">진행 중인 후속 조치가 없습니다.</p>
        )}
        <Link
          to={`/consultations/new?customerId=${customerId}`}
          className="rounded-xl border border-blue-200 px-4 py-2 text-center text-sm font-bold text-blue-700 hover:bg-blue-50"
        >
          상담 워크스페이스로 이동
        </Link>
      </div>
    </section>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export function Customer360Page() {
  const { customerId = "" } = useParams();
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const detail = useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => getResource<CustomerDetail>(`/customers/${customerId}`),
    enabled: Boolean(customerId),
  });
  const customer = detail.data?.customer;

  return (
    <div className="grid gap-5">
      {/* Header */}
      <ApiPanel title="고객 360" error={detail.error}>
        <div className="grid gap-4 md:grid-cols-4">
          <Info label="고객" value={customer?.customer_name ?? customer?.customer_no ?? customer?.id ?? customerId} />
          <Info label="세그먼트" value={segmentLabel(customer?.segment_code)} />
          <Info label="위험등급" value={riskGradeLabel(customer?.risk_grade_code)} />
          <Info label="총자산" value={formatKrw(customer?.total_assets_krw)} />
        </div>

        {/* Synthetic notice */}
        {detail.data?.synthetic_customer_notice && (
          <div
            className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
            role="alert"
          >
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge statusCode={detail.data.synthetic_customer_notice.status_code} />
              <p className="font-semibold">{detail.data.synthetic_customer_notice.message}</p>
            </div>
          </div>
        )}
      </ApiPanel>

      {/* Tab bar */}
      <TabBar active={activeTab} onChange={setActiveTab} />

      {/* Tab panels */}
      <div
        id={`tab-panel-${activeTab}`}
        role="tabpanel"
        aria-label={TABS.find((t) => t.id === activeTab)?.label}
      >
        {activeTab === "overview" && (
          <OverviewTab detail={detail.data} customerId={customerId} />
        )}
        {activeTab === "portfolio" && (
          <PortfolioTab detail={detail.data} />
        )}
        {activeTab === "actions" && (
          <ActionsTab detail={detail.data} customerId={customerId} />
        )}
        {activeTab === "household" && (
          <HouseholdTab customerId={customerId} />
        )}
      </div>
    </div>
  );
}
