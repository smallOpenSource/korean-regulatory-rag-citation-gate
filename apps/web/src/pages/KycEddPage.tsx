/**
 * KycEddPage — Wave-Audit-Defect-Fix C2 (plan §6 line 367; OQ-1 + OQ-5)
 *
 * Surfaces 5 backend endpoints:
 *   - GET    /kyc-edd/triggers                  (list)
 *   - GET    /kyc-edd/triggers/{id}             (detail)
 *   - POST   /kyc-edd/triggers                  (evaluate / create — kyc_edd_triggered + kyc_edd_evaluated)
 *   - POST   /kyc-edd/triggers/{id}/reassess    (kyc_edd_reassessed)
 *   - POST   /kyc-edd/triggers/{id}/complete    (kyc_edd_completed — V060 split from kyc_edd_reassessed)
 *
 * Migration: V060 registers 4 new canonical action codes (kyc_edd_completed +
 * trigger_listed + trigger_detail_viewed + evaluated). The /complete emit was
 * previously misclassified as kyc_edd_reassessed at kyc_edd.py:184 — split is
 * the OQ-1 resolution.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge, StatusBadge } from "../components/Badges";
import { getResource, postResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import { statusLabel } from "../lib/labels";
import { useAuthStore } from "../store/auth";

// Service-viability F10: DB-level kyc_edd_triggers.status also exposes
// IN_PROGRESS (V060 lifecycle: OPEN → IN_PROGRESS → CLOSED). Audit Q5
// captured 8 rows in the live DOM split OPEN/IN_PROGRESS/CLOSED so the
// type narrowed previously to OPEN | CLOSED was incorrect and meant the
// status badge fell into the unmapped-schema-drift red branch.
type KycEddStatus = "OPEN" | "IN_PROGRESS" | "CLOSED";

interface KycEddTrigger {
  id: string;
  customer_id: string;
  trigger_code: string;
  status: KycEddStatus;
  triggered_at: string;
  closed_at: string | null;
  risk_score: number | null;
  rationale_redacted: string | null;
}

interface ListResponse {
  items: KycEddTrigger[];
  total: number;
}

// svc-viability-v3 B6 — align with backend SoT (kyc_edd.py:25 _require_compliance_role).
// PB removed (compliance role only); BRANCH_MANAGER added to match the
// backend's `{"ADMIN","WM","BRANCH_MANAGER"}` set. Frontend is UX hint;
// real RBAC stays on the server side.
const WRITE_ROLES = new Set(["ADMIN", "WM", "BRANCH_MANAGER"]);

export function KycEddPage() {
  const user = useAuthStore((s) => s.user);
  const roleCode = user?.roleCode ?? "";
  const canMutate = WRITE_ROLES.has(roleCode);
  const queryClient = useQueryClient();

  const listQuery = useQuery<ListResponse>({
    queryKey: ["kyc-edd-triggers"],
    queryFn: () => getResource<ListResponse>("/kyc-edd/triggers"),
  });

  const [customerId, setCustomerId] = useState("");
  const [triggerCode, setTriggerCode] = useState("");
  const [rationale, setRationale] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const detailQuery = useQuery<KycEddTrigger>({
    queryKey: ["kyc-edd-triggers", selectedId],
    queryFn: () => getResource<KycEddTrigger>(`/kyc-edd/triggers/${selectedId}`),
    enabled: !!selectedId,
  });

  const evaluateMutation = useMutation<
    KycEddTrigger,
    Error,
    { customer_id: string; trigger_code: string; rationale: string }
  >({
    mutationFn: (body) => postResource<KycEddTrigger>("/kyc-edd/evaluate", body),
    onSuccess: () => {
      setCustomerId("");
      setTriggerCode("");
      setRationale("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["kyc-edd-triggers"] });
    },
    onError: (err) => setError(err.message),
  });

  const reassessMutation = useMutation<KycEddTrigger, Error, string>({
    mutationFn: (id) => postResource<KycEddTrigger>(`/kyc-edd/triggers/${id}/reassess`, {}),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["kyc-edd-triggers"] });
    },
    onError: (err) => setError(err.message),
  });

  const completeMutation = useMutation<KycEddTrigger, Error, string>({
    mutationFn: (id) => postResource<KycEddTrigger>(`/kyc-edd/triggers/${id}/complete`, {}),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["kyc-edd-triggers"] });
    },
    onError: (err) => setError(err.message),
  });

  function handleEvaluate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!customerId.trim() || !triggerCode.trim()) {
      setError("customer_id 및 trigger_code는 필수입니다");
      return;
    }
    evaluateMutation.mutate({
      customer_id: customerId.trim(),
      trigger_code: triggerCode.trim(),
      rationale: rationale.trim(),
    });
  }

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-emerald-700 to-teal-700 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-emerald-100">
          KYC / EDD
        </p>
        <h1 className="mt-3 text-3xl font-black">강화된 고객확인 (EDD)</h1>
        <p className="mt-2 text-emerald-50 text-sm">
          특정금융정보법 EDD trigger 평가 + 재평가 + 종결. 모든 단계는
          audit_logs로 박제되며, /complete 종결 이벤트는 V060 부터
          kyc_edd_completed 로 별도 박제됩니다 (이전 kyc_edd_reassessed
          중복 문제 해소).
        </p>
      </section>

      {canMutate && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-bold text-slate-900">신규 EDD trigger 평가</h2>
          <form className="mt-4 grid gap-3" onSubmit={handleEvaluate}>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">customer_id</span>
              <input
                type="text"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="UUID"
                aria-required="true"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">trigger_code</span>
              <input
                type="text"
                value={triggerCode}
                onChange={(e) => setTriggerCode(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="예: HIGH_RISK_COUNTRY / PEP / UNUSUAL_PATTERN"
                aria-required="true"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">사유 (redacted)</span>
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={2}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={evaluateMutation.isPending}
              className="justify-self-start rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
            >
              {evaluateMutation.isPending ? "평가 중..." : "EDD 평가 등록"}
            </button>
          </form>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-900">EDD trigger 목록</h2>
        {listQuery.isPending && (
          <p className="mt-3 text-xs text-slate-500">로드 중...</p>
        )}
        {listQuery.isError && (
          <p className="mt-3 text-xs text-rose-700">
            목록 로드 실패: {listQuery.error.message}
          </p>
        )}
        {listQuery.data && listQuery.data.items.length === 0 && (
          <p className="mt-3 text-xs text-slate-500">등록된 EDD trigger 없음</p>
        )}
        {listQuery.data && listQuery.data.items.length > 0 && (
          <ul className="mt-3 grid gap-2" role="list">
            {listQuery.data.items.map((row) => (
              <li
                key={row.id}
                className={`grid gap-1 rounded-xl border p-3 text-xs ${
                  selectedId === row.id
                    ? "border-emerald-300 bg-emerald-50"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedId(row.id)}
                    className="rounded bg-white px-2 py-0.5 font-mono text-xs font-bold text-slate-700 hover:bg-slate-100"
                  >
                    {row.id.slice(0, 8)}
                  </button>
                  <StatusBadge statusCode={row.status} />
                  <Badge tone="blue">{row.trigger_code}</Badge>
                </div>
                <div className="text-slate-500">
                  고객 {row.customer_id.slice(0, 8)} · 평가:{" "}
                  {formatBankerTimestamp(row.triggered_at)}
                  {row.closed_at && (
                    <> · 종결: {formatBankerTimestamp(row.closed_at)}</>
                  )}
                </div>
                {canMutate && (row.status === "OPEN" || row.status === "IN_PROGRESS") && (
                  <div className="mt-1 flex gap-2">
                    {/* svc-viability-v3 B7 — reassess SQL is OPEN-only
                        (repositories/kyc_edd.py:53), complete SQL accepts
                        OPEN+IN_PROGRESS (:67). The button gating mirrors
                        the SQL asymmetry per ADR-014. */}
                    {row.status === "OPEN" && (
                      <button
                        type="button"
                        onClick={() => reassessMutation.mutate(row.id)}
                        disabled={reassessMutation.isPending}
                        className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
                      >
                        재평가
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => completeMutation.mutate(row.id)}
                      disabled={completeMutation.isPending}
                      className="rounded border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
                    >
                      종결
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {detailQuery.data && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-bold text-slate-900">
            상세 — {detailQuery.data.id.slice(0, 8)}
          </h2>
          <dl className="mt-3 grid gap-2 text-xs text-slate-700">
            <div>
              <dt className="font-semibold">trigger_code</dt>
              <dd>{detailQuery.data.trigger_code}</dd>
            </div>
            <div>
              <dt className="font-semibold">상태</dt>
              <dd>{statusLabel(detailQuery.data.status)}</dd>
            </div>
            <div>
              <dt className="font-semibold">risk_score</dt>
              <dd>{detailQuery.data.risk_score ?? "—"}</dd>
            </div>
            {detailQuery.data.rationale_redacted && (
              <div>
                <dt className="font-semibold">사유 (redacted)</dt>
                <dd className="whitespace-pre-wrap rounded bg-slate-50 p-2">
                  {detailQuery.data.rationale_redacted}
                </dd>
              </div>
            )}
          </dl>
        </section>
      )}
    </div>
  );
}
