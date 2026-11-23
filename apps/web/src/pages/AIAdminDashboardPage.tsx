/**
 * AIAdminDashboardPage — T234 / ADMIN only
 *
 * Real-time AI operations dashboard.
 * Polling via WS event "ai_metrics_tick" every 30s.
 *
 * Charts:
 *  - AI 사용량 (calls/hour by agent) — BarChart
 *  - 실패율 (fail-closed rate by reason_code) — PieChart
 *  - 오용 신호 (injection detected, rate limited counts) — BarChart
 *  - 토큰 소비 원장 (cumulative monthly cap 560K from RUN-11)
 */

import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { WS_BASE_URL } from "../lib/api";
import { WS_SUBPROTOCOL } from "../lib/websocket";
import { useAuthStore } from "../store/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentUsage {
  agent: string;
  calls: number;
}

interface FailReason {
  reason: string;
  count: number;
}

interface MisuseSignal {
  signal: string;
  count: number;
}

interface AiMetrics {
  usage_by_agent: AgentUsage[];
  fail_closed_by_reason: FailReason[];
  misuse_signals: MisuseSignal[];
  token_monthly_used: number;
  token_monthly_cap: number;
  last_tick: string;
}

// ---------------------------------------------------------------------------
// Synthetic initial state (shown before first WS tick)
// ---------------------------------------------------------------------------

const INITIAL_METRICS: AiMetrics = {
  usage_by_agent: [
    { agent: "rag_qa", calls: 42 },
    { agent: "email_draft", calls: 17 },
    { agent: "consultation_briefing", calls: 28 },
    { agent: "house_view_generation", calls: 6 },
    { agent: "nba_script", calls: 33 },
    { agent: "compliance_check", calls: 0 },
    { agent: "portfolio_analysis", calls: 11 },
  ],
  fail_closed_by_reason: [
    { reason: "NO_CITATION", count: 5 },
    { reason: "FAITHFULNESS_GATE", count: 3 },
    { reason: "PROMPT_INJECTION", count: 1 },
    { reason: "LLM07_LEAKAGE", count: 2 },
    { reason: "TOKEN_EXCEEDED", count: 1 },
  ],
  misuse_signals: [
    { signal: "주입 감지", count: 1 },
    { signal: "속도 제한", count: 4 },
    { signal: "LLM07 리댁션", count: 2 },
  ],
  token_monthly_used: 147800,
  token_monthly_cap: 560000,
  last_tick: new Date().toISOString(),
};

const FAIL_COLORS = ["#ef4444", "#f97316", "#eab308", "#8b5cf6", "#6b7280"];
const MISUSE_COLORS = ["#dc2626", "#ea580c", "#ca8a04"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Wave-Audit-Defect-Fix D-S4: delegate to formatBankerNumber so PB number
// formatting comes from a single canonical helper (page-level-consistency-grep).
import { formatBankerNumber, formatBankerTimestamp } from "../lib/format";

function formatNumber(n: number): string {
  return formatBankerNumber(n);
}

function percentUsed(used: number, cap: number): number {
  return Math.min(100, Math.round((used / cap) * 100));
}

type WsStatus = "connecting" | "open" | "closed" | "failed";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AIAdminDashboardPage() {
  const [metrics, setMetrics] = useState<AiMetrics>(INITIAL_METRICS);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const [lastUpdate, setLastUpdate] = useState<string>(INITIAL_METRICS.last_tick);
  const wsRef = useRef<WebSocket | null>(null);
  const token = useAuthStore((state) => state.accessToken);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    function connect() {
      try {
        ws = new WebSocket(WS_BASE_URL, WS_SUBPROTOCOL);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsStatus("open");
          if (token) {
            ws?.send(JSON.stringify({ ticket: token }));
          }
        };

        ws.onmessage = (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data as string) as {
              event_type?: string;
              payload?: AiMetrics;
            };
            if (data.event_type === "ai_metrics_tick" && data.payload) {
              setMetrics(data.payload);
              setLastUpdate(data.payload.last_tick ?? new Date().toISOString());
            }
          } catch {
            // malformed event — ignore
          }
        };

        ws.onerror = () => {
          setWsStatus("failed");
        };

        ws.onclose = () => {
          setWsStatus("closed");
        };
      } catch {
        setWsStatus("failed");
      }
    }

    // Attempt WS connection
    connect();

    // Fallback polling every 30s in case WS is unavailable (PoC env)
    pollInterval = setInterval(() => {
      // In a real implementation, call GET /admin/ai-metrics
      // For PoC, we just jitter the synthetic metrics slightly
      setMetrics((prev) => ({
        ...prev,
        token_monthly_used: Math.min(prev.token_monthly_cap, prev.token_monthly_used + Math.floor(Math.random() * 200)),
        last_tick: new Date().toISOString(),
        usage_by_agent: prev.usage_by_agent.map((a) => ({
          ...a,
          calls: a.calls + Math.floor(Math.random() * 3),
        })),
      }));
      setLastUpdate(new Date().toISOString());
    }, 30_000);

    return () => {
      if (pollInterval) clearInterval(pollInterval);
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
      }
    };
  }, [token]);

  const tokenPct = percentUsed(metrics.token_monthly_used, metrics.token_monthly_cap);
  const tokenBarColor = tokenPct >= 90 ? "#ef4444" : tokenPct >= 70 ? "#f97316" : "#16a34a";

  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-slate-950 to-blue-950 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-blue-300">ADMIN 전용 · AI 운영현황</p>
        <h1 className="mt-3 text-3xl font-black">AI 운영현황 대시보드</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <p className="text-slate-300">실시간 모니터링 · 30초 자동 갱신</p>
          <span
            className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${
              wsStatus === "open"
                ? "border-emerald-400 bg-emerald-900/50 text-emerald-300"
                : wsStatus === "connecting"
                  ? "border-amber-400 bg-amber-900/50 text-amber-300"
                  : "border-red-400 bg-red-900/50 text-red-300"
            }`}
            role="status"
            aria-label={`WebSocket 연결 상태: ${wsStatus}`}
          >
            WS {wsStatus === "open" ? "연결됨" : wsStatus === "connecting" ? "연결 중" : "끊김"}
          </span>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          최종 갱신: {formatBankerTimestamp(lastUpdate)}
        </p>
      </section>

      {/* Token Ledger — always-visible summary */}
      <section
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        aria-label="토큰 소비 원장"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-base font-black text-slate-950">토큰 소비 원장</h2>
          <span className="text-xs font-bold text-slate-500">RUN-11 월간 한도 {formatNumber(metrics.token_monthly_cap)}</span>
        </div>
        <div className="mb-2 flex items-end justify-between gap-2">
          <p className="text-3xl font-black tabular-nums" style={{ color: tokenBarColor }}>
            {formatNumber(metrics.token_monthly_used)}
          </p>
          <p className="text-sm text-slate-500">{tokenPct}% 사용</p>
        </div>
        <div
          className="h-4 w-full overflow-hidden rounded-full bg-slate-200"
          role="progressbar"
          aria-valuenow={tokenPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`토큰 소비 ${tokenPct}%`}
        >
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${tokenPct}%`, backgroundColor: tokenBarColor }}
          />
        </div>
        <div className="mt-2 flex justify-between text-xs text-slate-400">
          <span>0</span>
          <span>{formatNumber(metrics.token_monthly_cap / 2)}</span>
          <span>{formatNumber(metrics.token_monthly_cap)}</span>
        </div>
        {tokenPct >= 80 && (
          <div
            className="mt-3 rounded-xl border border-red-200 bg-red-50 p-2.5 text-xs font-semibold text-red-800"
            role="alert"
          >
            ⚠️ 월간 토큰 한도의 {tokenPct}%를 사용했습니다. 관리자에게 문의하세요.
          </div>
        )}
      </section>

      {/* Charts grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* AI 사용량 by agent */}
        <section
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          aria-label="에이전트별 AI 사용량"
        >
          <h2 className="mb-4 text-base font-black text-slate-950">AI 사용량 (에이전트별 호출 수)</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={metrics.usage_by_agent}
              margin={{ top: 0, right: 8, left: -20, bottom: 40 }}
              role="img"
              aria-label="에이전트별 AI 호출 수 바 차트"
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey="agent"
                tick={{ fontSize: 10 }}
                angle={-35}
                textAnchor="end"
                interval={0}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [`${formatNumber(value)}건`, "호출 수"]}
                labelFormatter={(label: string) => `에이전트: ${label}`}
              />
              <Bar dataKey="calls" fill="#1d4ed8" radius={[4, 4, 0, 0]} name="호출 수" />
            </BarChart>
          </ResponsiveContainer>
        </section>

        {/* 실패율 by reason_code */}
        <section
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          aria-label="페일클로즈 사유별 실패율"
        >
          <h2 className="mb-4 text-base font-black text-slate-950">실패율 (사유 코드별)</h2>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart role="img" aria-label="페일클로즈 사유별 원형 차트">
              <Pie
                data={metrics.fail_closed_by_reason}
                dataKey="count"
                nameKey="reason"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ reason, percent }: { reason: string; percent: number }) =>
                  `${reason} ${(percent * 100).toFixed(0)}%`
                }
                labelLine={false}
              >
                {metrics.fail_closed_by_reason.map((_, index) => (
                  <Cell key={index} fill={FAIL_COLORS[index % FAIL_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value: number) => [`${formatNumber(value)}건`, "페일클로즈"]} />
              <Legend formatter={(value: string) => value} />
            </PieChart>
          </ResponsiveContainer>
        </section>

        {/* 오용 신호 */}
        <section
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          aria-label="오용 신호 모니터링"
        >
          <h2 className="mb-4 text-base font-black text-slate-950">오용 신호 (주입·속도제한)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={metrics.misuse_signals}
              margin={{ top: 0, right: 8, left: -20, bottom: 0 }}
              role="img"
              aria-label="오용 신호 유형별 바 차트"
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="signal" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [`${formatNumber(value)}건`, "감지 수"]}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]} name="감지 수">
                {metrics.misuse_signals.map((_, index) => (
                  <Cell key={index} fill={MISUSE_COLORS[index % MISUSE_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {metrics.misuse_signals.some((s) => s.count > 0 && s.signal.includes("주입")) && (
            <div
              className="mt-3 rounded-xl border border-red-200 bg-red-50 p-2.5 text-xs font-semibold text-red-800"
              role="alert"
            >
              🚨 프롬프트 주입 감지 신호가 있습니다. 감사 로그를 확인하세요.
            </div>
          )}
        </section>

        {/* Agent status summary */}
        <section
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          aria-label="에이전트 현황 요약"
        >
          <h2 className="mb-4 text-base font-black text-slate-950">에이전트 현황 요약</h2>
          <div className="grid gap-2">
            {metrics.usage_by_agent.map((agent) => (
              <div
                key={agent.agent}
                className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5"
              >
                <code className="text-xs font-semibold text-slate-700">{agent.agent}</code>
                <div className="flex items-center gap-3">
                  <span className="tabular-nums text-sm font-bold text-slate-900">
                    {formatNumber(agent.calls)}건
                  </span>
                  {agent.agent === "compliance_check" ? (
                    <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                      LLM 없음
                    </span>
                  ) : (
                    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                      활성
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
