/**
 * Right pane of ConsultationPage — 4-gate compliance panel + mini audit trail.
 * Extracted during Stage 2 T28 split (DEV-02). Behavior unchanged.
 */
import { useQuery } from "@tanstack/react-query";

import { Badge } from "./Badges";
import { getResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import { KO } from "../lib/i18n";
import { statusLabel } from "../lib/labels";
import { FourGateResult, GATE_LABEL } from "./ConsultationPaneTypes";

function gateTone(status: string): "green" | "red" | "yellow" {
  // T3-3 (F15): ACKNOWLEDGED는 PASSED → branch-manager acknowledge_gate 후속
  // lifecycle 상태 (V023:43 CHECK 포함). 시각적으로 PASSED와 동일한 green tone
  // 유지하여 raw enum이 yellow/PENDING으로 잘못 표현되지 않도록 한다.
  if (status === "PASSED" || status === "ACKNOWLEDGED") return "green";
  if (status === "BLOCKED") return "red";
  return "yellow";
}

function gateLabel(status: string): string {
  if (status === "PASSED") return KO.gate.pass;
  if (status === "ACKNOWLEDGED") return statusLabel("ACKNOWLEDGED");
  if (status === "BLOCKED") return KO.gate.block;
  return KO.gate.pending;
}

// Service-viability F6 / D3 (svc-follow-up-v1): per-gate pending hint
// directing users to the upstream pre-check action. Surfaces what
// `docs/api/API-04_four_gate_flow.md` documents so the PENDING state
// is actionable instead of silent.
function pendingHint(gateName: string): string {
  if (gateName === "suitability") {
    return "적합성 평가는 워크스페이스 적합성 폼에서 제출해주세요.";
  }
  if (gateName === "explanation") {
    return "설명의무 체크리스트를 검토하고 확인 버튼을 눌러주세요.";
  }
  if (gateName === "unfair_solicitation") {
    return "부당권유 점검은 상담 메시지 입력 후 검사 버튼에서 실행됩니다.";
  }
  if (gateName === "marketing") {
    return "광고심의는 마케팅 분류 이메일 초안을 제출하면 자동 평가됩니다.";
  }
  return "사전 점검이 필요합니다.";
}

export function ConsultationFourGatePane({
  consultationId,
  onAcknowledge,
  isBranchManager,
}: {
  consultationId: string;
  onAcknowledge: (gateName: string) => void;
  isBranchManager: boolean;
}) {
  const isNew = consultationId === "new";
  const { data, error, isLoading } = useQuery({
    queryKey: ["four-gate", consultationId],
    queryFn: () => getResource<FourGateResult>(`/consultations/${consultationId}/four-gate`),
    enabled: !isNew,
    refetchInterval: 30_000,
  });

  return (
    <div className="grid gap-3 p-1 pl-2">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-slate-900">{KO.gate.panel}</h2>
          {data && (
            <Badge tone={data.all_passed ? "green" : "yellow"}>
              {data.all_passed ? KO.gate.allPassed : KO.gate.notAllPassed}
            </Badge>
          )}
        </div>

        {isNew && (
          <p className="mt-3 text-xs text-slate-500">{KO.gate.notApplicable}</p>
        )}

        {!isNew && isLoading && (
          <div
            className="mt-3 space-y-2"
            role="status"
            aria-live="polite"
            aria-label="게이트 상태를 로드하고 있습니다"
          >
            <div className="h-3 w-32 animate-pulse rounded bg-slate-200" />
            <div className="h-3 w-48 animate-pulse rounded bg-slate-200" />
            <div className="h-3 w-40 animate-pulse rounded bg-slate-200" />
          </div>
        )}

        {!isNew && error && (
          <p className="mt-3 text-xs text-amber-800">{KO.gate.loadError}</p>
        )}

        {data && (
          <div className="mt-3 grid gap-2">
            {data.gates.map((gate) => (
              <div
                key={gate.gate_name}
                className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5"
              >
                <div>
                  <p className="text-sm font-semibold text-slate-800">
                    {GATE_LABEL[gate.gate_name] ?? gate.gate_name}
                  </p>
                  {gate.gate_acknowledged_at && (
                    <p className="text-xs text-slate-400">
                      확인: {formatBankerTimestamp(gate.gate_acknowledged_at)}
                    </p>
                  )}
                  {gate.gate_status === "PENDING" && !gate.gate_acknowledged_at && (
                    <p className="mt-0.5 text-xs text-amber-700">
                      {pendingHint(gate.gate_name)}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={gateTone(gate.gate_status)}>
                    {gateLabel(gate.gate_status)}
                  </Badge>
                  {isBranchManager && gate.gate_status === "PASSED" && !gate.gate_acknowledged_at && (
                    <button
                      type="button"
                      onClick={() => onAcknowledge(gate.gate_name)}
                      className="rounded-lg border border-blue-200 px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50"
                    >
                      {KO.gate.acknowledgeGate}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="mt-3 text-xs text-slate-400">{KO.gate.gateHelp}</p>
      </div>

      {data && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">{KO.consultation.auditTrail}</h3>
          <div className="grid gap-1.5">
            {data.gates
              .filter((g) => g.gate_acknowledged_at)
              .map((g) => (
                <div key={g.gate_name} className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                  <span className="font-semibold">{GATE_LABEL[g.gate_name]}</span>
                  <span className="text-slate-400">{statusLabel(g.gate_status)}</span>
                </div>
              ))}
            {data.gates.every((g) => !g.gate_acknowledged_at) && (
              <p className="text-xs text-slate-400">{KO.consultation.noAuditEvents}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
