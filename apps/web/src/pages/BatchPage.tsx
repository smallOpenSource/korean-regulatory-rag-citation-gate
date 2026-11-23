import { useQuery } from "@tanstack/react-query";

import { ApiPanel } from "../components/ApiPanel";
import { Badge, StatusBadge } from "../components/Badges";
import { getResource } from "../lib/api";
import { formatBankerNumber, formatBankerTimestamp } from "../lib/format";
import { jobTypeLabel, readinessCheckLabel, sourceLabel } from "../lib/labels";
import type { DomesticMarketStatus, DomesticTop200Coverage, ProviderMode } from "../lib/types";

interface BatchJob {
  id: string;
  job_name: string;
  job_type_code: string;
  status_code: string;
  started_at?: string;
  finished_at?: string;
  rows_collected?: number;
  rows_skipped?: number;
  rows_failed?: number;
  error_message?: string;
  provider_evidence?: BatchProviderEvidence[];
}

interface BatchProviderEvidence {
  id: string;
  provider_code: string;
  provider_status_code: string;
  target_ref: string;
  rows_collected: number;
  rows_skipped: number;
  rows_failed: number;
  reason_message?: string | null;
  provider_detail_json?: {
    source_code?: string | null;
    source_label?: string | null;
    source_policy_code?: string | null;
    source_policy_label?: string | null;
  };
  observed_at?: string;
}

interface BatchStatusResponse {
  items: BatchJob[];
  limit: number;
  offset: number;
  provider_mode?: ProviderMode;
}

interface DataReadiness {
  status_code: string;
  domestic_market?: DomesticMarketStatus;
  batch_status_summary: {
    running: number;
    done_recent: number;
    failed_recent: number;
    skipped_recent: number;
  };
  provider_mode?: ProviderMode;
}

function blockedMessage(job: BatchJob): string | null {
  if (job.status_code !== "FAILED" && job.status_code !== "SKIPPED") {
    return null;
  }
  const providerPrefix = job.job_type_code.startsWith("PROVIDER_") ? "공급자 수집" : "배치 작업";
  const statusCopy = job.status_code === "SKIPPED" ? "건너뜀(SKIPPED)" : "실패(FAILED)";
  const reason = job.error_message ?? "차단 근거를 안전하게 기록했습니다.";
  return `${providerPrefix}이 ${statusCopy}로 기록되었습니다. ${reason}`;
}

function providerEvidenceSourceLabel(evidence: BatchProviderEvidence): string {
  return sourceLabel(
    evidence.provider_detail_json?.source_code
      ?? evidence.provider_detail_json?.source_policy_code
      ?? evidence.provider_code,
  );
}

// Wave-Audit-Defect-Fix Wave D per-page: delegate to canonical helpers; legacy
// banned-pattern fallback replaced with the canonical 미확정 suffix.
function formatInteger(value?: number | null): string {
  return formatBankerNumber(typeof value === "number" ? value : null);
}

function formatPercent(value?: number | null): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "수치 미확정";
}

function Top200CoverageCard({ coverage }: { coverage?: DomesticTop200Coverage }) {
  if (!coverage) {
    return (
      <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
        상위 200개/30일 커버리지 근거가 아직 없습니다. 공식 KRX 수집·가공 배치가 완료되어야 준비 완료로 표시됩니다.
      </div>
    );
  }

  const tradingDays = Object.entries(coverage.expected_trading_days_by_market ?? {});

  return (
    <div className="mt-3 rounded-2xl border border-blue-100 bg-blue-50/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-900">시가총액 상위 200개 공식 KRX 커버리지</p>
          <p className="mt-1 text-sm text-slate-600">
            {coverage.message ?? "시가총액 상위 200개 기준의 30일 종목-거래일 커버리지를 검증합니다."}
          </p>
        </div>
        <StatusBadge statusCode={coverage.status_code} />
      </div>
      <div className="mt-3 grid gap-2 text-sm md:grid-cols-4">
        <MarketFact label="선택 종목" value={`${formatInteger(coverage.selected_count)} / ${formatInteger(coverage.required_count)}개`} />
        <MarketFact label="조회 기간" value={`최근 ${formatInteger(coverage.lookback_days)}일`} />
        <MarketFact label="종목-거래일 커버리지" value={`${formatInteger(coverage.observed_member_days)} / ${formatInteger(coverage.expected_member_days)}`} />
        <MarketFact label="커버리지 비율" value={formatPercent(coverage.coverage_ratio)} />
        <MarketFact label="누락 종목-거래일" value={formatInteger(coverage.missing_member_days)} />
        <MarketFact label="커버 종목" value={formatInteger(coverage.covered_tickers)} />
        <MarketFact label="KRX 기준시각" value={formatBankerTimestamp(coverage.latest_source_as_of)} />
        <MarketFact label="거래일 기준" value={coverage.resolved_trading_date ?? coverage.as_of_date ?? ""} />
      </div>
      {tradingDays.length ? (
        <p className="mt-3 text-xs text-slate-600">
          시장별 예상 거래일: {tradingDays.map(([market, days]) => `${market} ${days}일`).join(" · ")}
        </p>
      ) : null}
      {coverage.source_code || coverage.source_policy_code ? (
        <p className="mt-2 text-xs text-slate-600">
          출처 {sourceLabel(coverage.source_code)} · 정책 {sourceLabel(coverage.source_policy_code)}
        </p>
      ) : null}
      {(coverage.blocking_reasons ?? []).length ? (
        <div className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
          <p className="font-bold">차단 사유</p>
          <ul className="mt-1 list-disc pl-5">
            {(coverage.blocking_reasons ?? []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function BatchPage() {
  const jobs = useQuery({ queryKey: ["batch-status"], queryFn: () => getResource<BatchStatusResponse>("/batch/status") });
  const readiness = useQuery({ queryKey: ["batch-readiness"], queryFn: () => getResource<DataReadiness>("/data/readiness") });
  const items = jobs.data?.items ?? [];
  const providerMode = jobs.data?.provider_mode ?? readiness.data?.provider_mode;
  const domesticMarket = readiness.data?.domestic_market;

  return (
    <ApiPanel title="배치 모니터링" error={jobs.error}>
      <div className="mb-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-bold text-slate-900">공급자 준비 상태</p>
            <p className="mt-1 text-sm text-slate-600">건너뜀/실패 상태와 로컬 모드는 성공처럼 숨기지 않고 차단·주의 상태로 표시합니다.</p>
          </div>
          <StatusBadge statusCode={providerMode?.status_code ?? readiness.data?.status_code ?? "LOADING"} />
        </div>
        {providerMode ? (
          <div className="mt-3 grid gap-2 rounded-xl bg-white p-3 text-sm text-slate-700 md:grid-cols-3">
            <span>프로필 {providerMode.profile}</span>
            <span>엄격 모드 {providerMode.strict_external ? "켜짐" : "꺼짐"}</span>
            <span>필수 공급자 {providerMode.required_provider_codes.length ? providerMode.required_provider_codes.map(sourceLabel).join(", ") : "공급자 미확정"}</span>
            <p className="md:col-span-3">{providerMode.message}</p>
          </div>
        ) : null}
        {readiness.data ? (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Badge tone="blue">실행 중 {readiness.data.batch_status_summary.running}</Badge>
            <Badge tone="green">최근 24시간 완료 {readiness.data.batch_status_summary.done_recent}</Badge>
            <Badge tone="red">최근 24시간 실패 {readiness.data.batch_status_summary.failed_recent}</Badge>
            <Badge tone="orange">최근 24시간 건너뜀 {readiness.data.batch_status_summary.skipped_recent}</Badge>
          </div>
        ) : null}
        {readiness.error ? <p role="alert" className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">준비 상태 조회 실패: {readiness.error.message}</p> : null}
      </div>
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-bold text-slate-900">국내 시장 검증 상태</p>
            <p className="mt-1 text-sm text-slate-600">
              {domesticMarket?.message ?? "국내 시장 데이터의 기준시각·신선도·품질 상태를 불러오는 중입니다."}
            </p>
          </div>
          <StatusBadge statusCode={domesticMarket?.status_code ?? "LOADING"} />
        </div>
        <Top200CoverageCard coverage={domesticMarket?.top200_coverage} />
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {(domesticMarket?.checks ?? []).map((check) => (
            <div className="rounded-xl bg-slate-50 p-3 text-sm" key={check.check_code}>
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{readinessCheckLabel(check.check_code)}</span>
                <StatusBadge statusCode={check.status_code} />
              </div>
              <p className="mt-2 text-slate-600">{check.message}</p>
              {check.source_as_of || check.source_code ? (
                <p className="mt-2 text-xs text-slate-500">
                  출처 {sourceLabel(check.source_code)} · 기준시각 {formatBankerTimestamp(check.source_as_of)}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-3">
        {items.map((job) => (
          <article key={job.id} className="rounded-2xl border border-slate-200 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-bold">{jobTypeLabel(job.job_type_code)}</h2>
                <p className="text-sm text-slate-600">수집 {job.rows_collected ?? 0} · 건너뜀 {job.rows_skipped ?? 0} · 실패 {job.rows_failed ?? 0}</p>
              </div>
              <StatusBadge statusCode={job.status_code} />
            </div>
            {blockedMessage(job) ? <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">{blockedMessage(job)}</p> : null}
            {(job.provider_evidence ?? []).length ? (
              <div className="mt-3 grid gap-2">
                {(job.provider_evidence ?? []).map((evidence) => (
                  <div key={evidence.id} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold">{providerEvidenceSourceLabel(evidence)} · {evidence.target_ref}</span>
                      <StatusBadge statusCode={evidence.provider_status_code} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      수집 {evidence.rows_collected} · 건너뜀 {evidence.rows_skipped} · 실패 {evidence.rows_failed}
                      {evidence.observed_at ? ` · 관측 ${formatBankerTimestamp(evidence.observed_at)}` : ""}
                    </p>
                    {evidence.provider_detail_json?.source_policy_code ? (
                      <p className="mt-2 text-xs text-slate-600">
                        출처 정책 {sourceLabel(evidence.provider_detail_json.source_policy_code)}
                      </p>
                    ) : null}
                    {evidence.reason_message ? <p className="mt-2 text-xs text-slate-600">{evidence.reason_message}</p> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {items.length === 0 ? <p className="text-sm text-slate-500">배치 로그가 없습니다. 공급자 수집이 미실행 상태임을 명시적으로 확인하세요.</p> : null}
      </div>
    </ApiPanel>
  );
}

function MarketFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white p-3">
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <p className="mt-1 font-semibold text-slate-900">{value}</p>
    </div>
  );
}
