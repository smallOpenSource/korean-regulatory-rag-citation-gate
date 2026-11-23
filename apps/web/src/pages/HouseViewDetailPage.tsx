/**
 * House View Detail — T16 lifecycle
 * Version history sidebar, AI metadata block, prompt audit trail (redacted),
 * archive/activate controls (ADMIN via houseViewActivation route gate).
 */
import type { ReactNode } from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AiGeneratedBadge, StatusBadge } from "../components/Badges";
import { DevReference } from "../components/DevReference";
import { getResource, postResource } from "../lib/api";
import { canAccessRoute } from "../lib/access";
import { formatBankerTimestamp } from "../lib/format";
import { statusLabel } from "../lib/labels";
import { useAuthStore } from "../store/auth";
import type { ListResponse } from "../lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HouseViewDetail {
  id: string;
  title: string;
  period_code: string;
  version_no: number;
  status_code: string;
  summary?: string;
  ai_generated_at?: string;
  ai_model_name?: string;
  asset_views_json?: unknown;
  model_portfolios_json?: unknown;
  risks_json?: unknown;
  // lifecycle fields
  prompt_tokens?: number;
  completion_tokens?: number;
  inputs_hash?: string;
  confidence?: number;
  market?: string;
  asset_class?: string;
  region?: string;
  content?: unknown;
  // P2-3: AI-body data-quality signals surfaced from GET /house-views/{id}
  data_quality_notice?: string;
  faithfulness?: {
    passed?: boolean;
    flags?: string[];
    ungrounded_figures?: string[];
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const HOUSEVIEW_FIELD_LABELS: Record<string, string> = {
  primary_view: "주요 전망",
  tilt: "비중 조정",
  top_risks: "주요 리스크",
  target_allocation: "목표 배분",
  allocations: "자산 배분",
  asset_class: "자산 유형",
  weight: "비중",
  rationale: "근거",
  name: "명칭",
  description: "설명",
  confidence: "신뢰도",
  horizon: "기간 전망",
  outlook: "전망 의견",
  level: "수준",
  category: "분류",
  benchmark: "기준 지표",
  rebalance_band: "리밸런싱 허용 폭",
  risk_factor: "위험 요인",
  mitigation: "완화 방안",
  region: "지역",
  sector: "업종",
};

function renderHouseViewValue(value: unknown): ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-slate-400">기재 없음</span>;
  }
  if (typeof value === "number") {
    return value.toString();
  }
  if (typeof value === "boolean") {
    return value ? "예" : "아니오";
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-slate-400">기재 없음</span>;
    }
    return (
      <ul className="list-disc space-y-1 pl-5">
        {value.map((item, idx) => (
          <li key={idx}>{renderHouseViewValue(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className="text-slate-400">기재 없음</span>;
    }
    return (
      <dl className="grid gap-1.5 sm:grid-cols-[max-content_1fr] sm:gap-x-4">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-semibold text-slate-600">
              {HOUSEVIEW_FIELD_LABELS[k] ?? k}
            </dt>
            <dd className="text-slate-700">{renderHouseViewValue(v)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return String(value);
}

function JsonSection({ title, value }: { title: string; value: unknown }) {
  // Backend serializes JSONB columns as a stringified payload (e.g. "{}"),
  // so we parse first; if parsing fails we keep the original value as a
  // best-effort fallback before deciding whether it should render as "empty".
  // Raw JSON.stringify exposes DB-column-style field names (primary_view,
  // top_risks, tilt) which v8 v2 panel cycle 3 flagged as BANNED — render as
  // Korean-labeled key/value tree instead.
  let parsed: unknown = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch {
      parsed = value;
    }
  }
  const isEmpty =
    parsed === undefined ||
    parsed === null ||
    (typeof parsed === "string" && parsed.trim() === "") ||
    (typeof parsed === "object" &&
      !Array.isArray(parsed) &&
      Object.keys(parsed as Record<string, unknown>).length === 0) ||
    (Array.isArray(parsed) && parsed.length === 0);
  return (
    <section className="rounded-2xl bg-slate-50 p-4">
      <h3 className="font-bold text-slate-800">{title}</h3>
      {isEmpty ? (
        <p className="mt-2 rounded-lg bg-white p-3 text-xs text-slate-500">
          AI 생성 콘텐츠가 아직 채워지지 않았습니다. 생성 또는 검토 단계에서 채워집니다.
        </p>
      ) : (
        <div className="mt-2 rounded-lg bg-white p-3 text-xs leading-relaxed text-slate-600">
          {renderHouseViewValue(parsed)}
        </div>
      )}
    </section>
  );
}

function MetadataBlock({ detail }: { detail: HouseViewDetail }) {
  // Only include rows where data is actually present — no dash/em-dash placeholders.
  const rows: Array<{ label: string; value: string | number }> = [
    ...(detail.ai_model_name != null ? [{ label: "AI 모델", value: detail.ai_model_name }] : []),
    ...(detail.ai_generated_at ? [{ label: "생성 일시", value: formatBankerTimestamp(detail.ai_generated_at) }] : []),
    ...(detail.confidence != null ? [{ label: "신뢰도", value: `${(detail.confidence * 100).toFixed(0)}%` }] : []),
    ...(detail.prompt_tokens != null ? [{ label: "프롬프트 토큰", value: detail.prompt_tokens }] : []),
    ...(detail.completion_tokens != null ? [{ label: "컴플리션 토큰", value: detail.completion_tokens }] : []),
    { label: "버전", value: `v${detail.version_no}` },
    { label: "기간 코드", value: detail.period_code },
    ...(detail.market ? [{ label: "시장", value: detail.market }] : []),
    ...(detail.asset_class ? [{ label: "자산 유형", value: detail.asset_class }] : []),
  ];

  return (
    <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
      <p className="mb-3 text-xs font-bold uppercase tracking-wider text-blue-700">AI 생성 메타데이터</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {rows.map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="text-sm font-semibold text-slate-800">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function PromptAuditTrail({ detail }: { detail: HouseViewDetail }) {
  return (
    <details className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <summary className="cursor-pointer select-none text-sm font-semibold text-slate-700">
        프롬프트 감사 추적 (일부 마스킹됨)
      </summary>
      <div className="mt-3 space-y-2 text-xs text-slate-600">
        <p className="rounded-lg bg-white p-3">
          <span className="font-bold">입력 해시 (inputs_hash):</span>{" "}
          {detail.inputs_hash ? `${detail.inputs_hash.slice(0, 16)}${"*".repeat(16)}` : "정보 없음"}
        </p>
        <p className="rounded-lg bg-amber-50 p-3 text-amber-700">
          실제 프롬프트 내용은 규정에 따라 마스킹됩니다. 전체 내용은 감사 로그에서 권한 내에서 열람 가능합니다.
          <DevReference inline="ADR-005" />
        </p>
        <p className="rounded-lg bg-white p-3">
          <span className="font-bold">프롬프트 토큰:</span> {detail.prompt_tokens ?? "정보 없음"} /{" "}
          <span className="font-bold">컴플리션 토큰:</span> {detail.completion_tokens ?? "정보 없음"}
        </p>
      </div>
    </details>
  );
}

function VersionHistorySidebar({
  currentId,
  periodCode,
}: {
  currentId: string;
  periodCode: string;
}) {
  const allViews = useQuery({
    queryKey: ["house-views-all"],
    queryFn: () => getResource<ListResponse<HouseViewDetail>>("/house-views?limit=100"),
  });

  const related = (allViews.data?.items ?? []).filter((v) => v.period_code === periodCode);

  return (
    <aside className="w-full rounded-2xl border border-slate-200 bg-white p-4 lg:w-64 lg:shrink-0">
      <h3 className="mb-3 text-sm font-bold text-slate-700">버전 이력</h3>
      {allViews.isLoading && <p className="text-xs text-slate-400">불러오는 중…</p>}
      <ul className="grid gap-1.5">
        {related.map((v) => {
          const isActive = v.id === currentId;
          return (
            <li key={v.id}>
              <Link
                to={`/house-views/${v.id}`}
                className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-blue-700 text-white font-bold"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
                aria-current={isActive ? "page" : undefined}
              >
                <span className="truncate">v{v.version_no} · {v.period_code}</span>
                <span
                  className={`ml-2 shrink-0 rounded-full px-1.5 py-0.5 text-xs font-semibold ${
                    isActive
                      ? "bg-blue-600 text-white"
                      : v.status_code === "ACTIVATED"
                        ? "bg-emerald-100 text-emerald-700"
                        : v.status_code === "ARCHIVED"
                          ? "bg-slate-200 text-slate-600"
                          : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {statusLabel(v.status_code)}
                </span>
              </Link>
            </li>
          );
        })}
        {related.length === 0 && !allViews.isLoading && (
          <li className="text-xs text-slate-400 px-2">같은 기간의 이력이 없습니다.</li>
        )}
      </ul>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function HouseViewDetailPage({ activation }: { activation?: boolean }) {
  const { houseViewId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canManage = user ? canAccessRoute(user.roleCode, "houseViewActivation") : false;

  const detail = useQuery({
    queryKey: ["house-view", houseViewId],
    queryFn: () => getResource<HouseViewDetail>(`/house-views/${houseViewId}`),
    enabled: Boolean(houseViewId),
  });

  const reviewMutation = useMutation({
    mutationFn: () =>
      postResource<HouseViewDetail>(
        `/house-views/${houseViewId}/review`,
        undefined,
        { idempotencyKey: crypto.randomUUID() },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["house-view"] });
      void queryClient.invalidateQueries({ queryKey: ["house-views-all"] });
    },
  });

  const activateMutation = useMutation({
    mutationFn: () =>
      postResource<HouseViewDetail>(
        `/house-views/${houseViewId}/activate-lifecycle`,
        undefined,
        { idempotencyKey: crypto.randomUUID() },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["house-view"] });
      void queryClient.invalidateQueries({ queryKey: ["house-views-all"] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () =>
      postResource<HouseViewDetail>(`/house-views/${houseViewId}/archive`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["house-view"] });
      void queryClient.invalidateQueries({ queryKey: ["house-views-all"] });
      void navigate("/house-views");
    },
  });

  const [marketDataSummary, setMarketDataSummary] = useState("");
  const generateMutation = useMutation({
    mutationFn: () =>
      postResource<HouseViewDetail>(
        `/house-views/${houseViewId}/generate-content`,
        { market_data_summary: marketDataSummary, previous_house_view_summary: "" },
        { idempotencyKey: crypto.randomUUID() },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["house-view"] });
      void queryClient.invalidateQueries({ queryKey: ["house-views-all"] });
    },
  });

  const hv = detail.data;

  if (detail.isLoading) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-slate-400">불러오는 중…</div>
    );
  }

  if (detail.error || !hv) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
          하우스뷰를 불러오지 못했습니다.
        </p>
      </div>
    );
  }

  const lifecycleStatus = hv.status_code;
  const canGenerate = canManage && lifecycleStatus === "DRAFT";
  const canReview = canManage && lifecycleStatus === "GENERATED";
  const canActivate = canManage && lifecycleStatus === "REVIEWED";
  const canArchive = canManage && (lifecycleStatus === "ACTIVATED" || lifecycleStatus === "ACTIVE");

  return (
    <div className="grid gap-6">
      {/* Page header */}
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
        <Link to="/house-views" className="hover:text-blue-700">하우스뷰 목록</Link>
        <span aria-hidden="true">›</span>
        <span className="text-slate-700 font-semibold truncate">{hv.title}</span>
      </div>

      <div className="flex flex-wrap gap-6 lg:flex-nowrap">
        {/* Version history sidebar */}
        <VersionHistorySidebar currentId={houseViewId} periodCode={hv.period_code} />

        {/* Main content */}
        <div className="min-w-0 flex-1 space-y-5">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h1 className="text-2xl font-black text-slate-950">{hv.title}</h1>
                <p className="mt-1 text-sm text-slate-500">
                  v{hv.version_no} · {hv.period_code}
                  {hv.market ? ` · ${hv.market}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <StatusBadge statusCode={hv.status_code} />
                {hv.ai_generated_at && hv.ai_model_name && (
                  <AiGeneratedBadge generatedAt={hv.ai_generated_at} modelName={hv.ai_model_name} />
                )}
              </div>
            </div>

            {hv.summary && (
              <p className="mt-4 text-sm leading-relaxed text-slate-700">{hv.summary}</p>
            )}

            {/* P2-3: AI-body data-quality disclosure + faithfulness — a house view
                summary is a synthetic AI market view, not a verified house view. */}
            {hv.data_quality_notice && (
              <div
                className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
                role="note"
                data-testid="house-view-data-quality-notice"
              >
                <span className="font-bold">데이터 품질 고지: </span>
                <span>{hv.data_quality_notice}</span>
              </div>
            )}
            {hv.faithfulness && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs" data-testid="house-view-faithfulness">
                <span
                  className={`rounded-full px-2 py-0.5 font-bold ${
                    hv.faithfulness.passed
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  근거충실성: {hv.faithfulness.passed ? "확인" : "검토 필요"}
                </span>
                {(hv.faithfulness.ungrounded_figures ?? []).length > 0 && (
                  <span className="text-amber-700">
                    ({(hv.faithfulness.ungrounded_figures ?? []).join(", ")})
                  </span>
                )}
              </div>
            )}

            {/* Admin controls */}
            {canManage && (
              <div className="mt-5 flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="w-full text-xs font-bold text-slate-500 uppercase tracking-wider">관리자 제어 (T16)</p>
                {canGenerate && (
                  <div className="w-full space-y-2">
                    <label className="block text-xs font-semibold text-slate-700">
                      시장 데이터 요약 (선택)
                    </label>
                    <textarea
                      value={marketDataSummary}
                      onChange={(e) => setMarketDataSummary(e.target.value)}
                      placeholder="예: 코스피 2,650p / 미연준 금리 동결 시그널 / 원-달러 1,335원"
                      rows={2}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
                      disabled={generateMutation.isPending}
                    />
                    <button
                      type="button"
                      disabled={generateMutation.isPending}
                      onClick={() => generateMutation.mutate()}
                      className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-bold text-white hover:bg-purple-700 disabled:opacity-50"
                    >
                      {generateMutation.isPending ? "AI 생성 중…" : "AI 콘텐츠 생성 (DRAFT → GENERATED)"}
                    </button>
                    {generateMutation.error && (
                      <p role="alert" className="rounded-xl bg-red-50 p-2 text-sm text-red-700">
                        AI 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.
                      </p>
                    )}
                  </div>
                )}
                {canReview && (
                  <button
                    type="button"
                    disabled={reviewMutation.isPending}
                    onClick={() => reviewMutation.mutate()}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    검토 완료 (GENERATED → REVIEWED)
                  </button>
                )}
                {canActivate && (
                  <button
                    type="button"
                    disabled={activateMutation.isPending}
                    onClick={() => activateMutation.mutate()}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    활성화 (REVIEWED → ACTIVATED)
                  </button>
                )}
                {canArchive && (
                  <button
                    type="button"
                    disabled={archiveMutation.isPending}
                    onClick={() => archiveMutation.mutate()}
                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                  >
                    아카이브
                  </button>
                )}
                {!canGenerate && !canReview && !canActivate && !canArchive && (
                  <p className="text-sm text-slate-500">
                    현재 상태({statusLabel(lifecycleStatus)})에서 가능한 관리자 조치가 없습니다.
                  </p>
                )}
                {(activateMutation.error ?? archiveMutation.error) && (
                  <p role="alert" className="w-full rounded-xl bg-red-50 p-2 text-sm text-red-700">
                    처리 중 오류가 발생했습니다.
                  </p>
                )}
              </div>
            )}

            {activation && !canManage && (
              <p role="alert" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
                이 기능은 관리자(ADMIN)만 사용할 수 있습니다.
              </p>
            )}
          </section>

          {/* AI metadata block */}
          {hv.status_code === "DRAFT" && !hv.ai_generated_at ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-700">초안 단계 · AI 콘텐츠 생성 전</p>
              <p className="mt-1 text-xs text-amber-600">AI 생성이 완료되면 메타데이터가 채워집니다.</p>
            </div>
          ) : (hv.ai_generated_at ?? hv.prompt_tokens) ? (
            <MetadataBlock detail={hv} />
          ) : null}

          {/* Prompt audit trail */}
          {hv.inputs_hash && <PromptAuditTrail detail={hv} />}

          {/* JSON sections */}
          <div className="grid gap-4 md:grid-cols-3">
            <JsonSection title="자산 전망" value={hv.asset_views_json} />
            <JsonSection title="모델 포트폴리오" value={hv.model_portfolios_json} />
            <JsonSection title="주요 리스크" value={hv.risks_json} />
          </div>

          {/* AI-generated content */}
          {hv.content !== undefined && hv.content !== null && (
            <section className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
              <h3 className="mb-2 font-bold text-blue-800">AI 생성 콘텐츠</h3>
              <pre className="overflow-auto rounded-lg bg-white p-3 text-xs leading-relaxed text-slate-600">
                {JSON.stringify(hv.content as Record<string, unknown>, null, 2)}
              </pre>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
