/**
 * DataGovernancePage — Wave-Audit-Defect-Fix C5 (plan §6 line 370)
 *
 * Surfaces 3 data-governance endpoints:
 *   - POST /purge-schedule    (REG-01 §20-2 파기 — emits canonical
 *                              credit_info_purge_simulated, audit.py:72)
 *   - GET  /purge-schedule    (list)
 *   - GET  /pseudonym-metadata (pseudonym label + re-identification risk note)
 *
 * Role gate (mirrors backend purge_svc.schedule_purge ADMIN-only path):
 *   - ADMIN: full read + create purge
 *   - AUDIT_VIEWER: read-only (list + pseudonym metadata)
 *   - PB / WM / BRANCH_MANAGER: read-only
 *
 * Note: the plan mentions `pseudonym_metadata_viewed` + `purge_schedule_created`
 * action codes. Backend currently emits the established canonical
 * `credit_info_purge_simulated` on POST and does not emit on the GET reads;
 * those extra audit codes are tracked under Wave C C2 scope (V060 migration).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badges";
import { getResource, postResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import { useAuthStore } from "../store/auth";

interface PurgeScheduleRow {
  id: string;
  target_table: string;
  target_row_id: string | null;
  purge_due_at: string | null;
  executed_at: string | null;
  purge_reason: string;
  synthetic?: boolean;
}

interface PurgeScheduleListResponse {
  items: PurgeScheduleRow[];
  count: number;
  synthetic?: boolean;
}

interface PseudonymMetadataResponse {
  pseudonym_label: string;
  applies_to?: string[];
  reidentification_risk_note: string;
  statutory_basis?: string;
  poc_deferred?: string;
  synthetic?: boolean;
}

interface PurgeRequest {
  customer_id: string;
  target_table: string;
  target_row_id?: string;
  reason?: string;
}

export function DataGovernancePage() {
  const user = useAuthStore((s) => s.user);
  const roleCode = user?.roleCode ?? "";
  const canCreatePurge = roleCode === "ADMIN";
  const queryClient = useQueryClient();

  const purgeListQuery = useQuery<PurgeScheduleListResponse>({
    queryKey: ["purge-schedule"],
    queryFn: () => getResource<PurgeScheduleListResponse>("/data-governance/purge-schedule"),
  });

  const pseudonymQuery = useQuery<PseudonymMetadataResponse>({
    queryKey: ["pseudonym-metadata"],
    queryFn: () => getResource<PseudonymMetadataResponse>("/data-governance/pseudonym-metadata"),
  });

  const [customerId, setCustomerId] = useState("");
  const [targetTable, setTargetTable] = useState("");
  const [targetRowId, setTargetRowId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation<PurgeScheduleRow, Error, PurgeRequest>({
    mutationFn: (body) => postResource<PurgeScheduleRow>("/data-governance/purge-schedule", body),
    onSuccess: () => {
      setCustomerId("");
      setTargetTable("");
      setTargetRowId("");
      setReason("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["purge-schedule"] });
    },
    onError: (err) => setError(err.message),
  });

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!customerId.trim() || !targetTable.trim()) {
      setError("customer_id 및 target_table은 필수입니다");
      return;
    }
    createMutation.mutate({
      customer_id: customerId.trim(),
      target_table: targetTable.trim(),
      target_row_id: targetRowId.trim() || undefined,
      reason: reason.trim() || undefined,
    });
  }

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-slate-800 to-cyan-700 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-100">
          Data Governance
        </p>
        <h1 className="mt-3 text-3xl font-black">개인정보·신용정보 거버넌스</h1>
        <p className="mt-2 text-cyan-50 text-sm">
          신용정보법 §20-2 파기 시뮬레이션 + 가명처리 메타데이터. ADMIN 만 파기
          스케줄을 등록할 수 있으며, 다른 역할은 감사 목적의 read-only 뷰입니다.
        </p>
      </section>

      <section
        aria-labelledby="pseudonym-meta"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2 id="pseudonym-meta" className="text-base font-bold text-slate-900">
          가명처리 메타데이터
        </h2>
        {pseudonymQuery.isPending && (
          <p className="mt-3 text-xs text-slate-500">로드 중...</p>
        )}
        {pseudonymQuery.isError && (
          <p className="mt-3 text-xs text-rose-700">
            로드 실패: {pseudonymQuery.error.message}
          </p>
        )}
        {pseudonymQuery.data && (
          <dl className="mt-3 grid gap-2 text-sm text-slate-700">
            <div className="grid grid-cols-[max-content_1fr] gap-2">
              <dt className="font-semibold">Pseudonym Label</dt>
              <dd className="font-mono">{pseudonymQuery.data.pseudonym_label}</dd>
            </div>
            <div className="grid gap-1">
              <dt className="font-semibold">재식별 위험 고지</dt>
              <dd className="rounded bg-amber-50 p-3 text-xs text-amber-900">
                {pseudonymQuery.data.reidentification_risk_note}
              </dd>
            </div>
          </dl>
        )}
      </section>

      {canCreatePurge && (
        <section
          aria-labelledby="purge-form"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2 id="purge-form" className="text-base font-bold text-slate-900">
            파기 스케줄 등록 (ADMIN 전용)
          </h2>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">고객 ID</span>
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
              <span className="font-semibold text-slate-700">target_table</span>
              <input
                type="text"
                value={targetTable}
                onChange={(e) => setTargetTable(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="예: ai_outputs"
                aria-required="true"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">target_row_id (선택)</span>
              <input
                type="text"
                value={targetRowId}
                onChange={(e) => setTargetRowId(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">사유</span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
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
              disabled={createMutation.isPending}
              className="justify-self-start rounded-xl border border-cyan-300 bg-cyan-50 px-4 py-2 text-sm font-semibold text-cyan-800 hover:bg-cyan-100 disabled:opacity-50"
            >
              {createMutation.isPending ? "등록 중..." : "파기 스케줄 등록"}
            </button>
          </form>
        </section>
      )}

      <section
        aria-labelledby="purge-list"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2 id="purge-list" className="text-base font-bold text-slate-900">
          파기 스케줄 목록
        </h2>
        {purgeListQuery.isPending && (
          <p className="mt-3 text-xs text-slate-500">로드 중...</p>
        )}
        {purgeListQuery.isError && (
          <p className="mt-3 text-xs text-rose-700">
            목록 로드 실패: {purgeListQuery.error.message}
          </p>
        )}
        {purgeListQuery.data && purgeListQuery.data.items.length === 0 && (
          <p className="mt-3 text-xs text-slate-500">등록된 파기 스케줄이 없습니다.</p>
        )}
        {purgeListQuery.data && purgeListQuery.data.items.length > 0 && (
          <ul className="mt-3 grid gap-2" role="list">
            {purgeListQuery.data.items.map((row) => (
              <li
                key={row.id}
                className="grid gap-1 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-white px-2 py-0.5 font-bold text-slate-600">
                    {row.id.slice(0, 8)}
                  </code>
                  <Badge tone="blue">{row.target_table}</Badge>
                </div>
                <div className="text-slate-500">
                  대상 row: {row.target_row_id ? row.target_row_id.slice(0, 8) : "—"} · 예정:{" "}
                  {row.purge_due_at ? formatBankerTimestamp(row.purge_due_at) : "—"}
                  {row.executed_at ? ` · 실행: ${formatBankerTimestamp(row.executed_at)}` : ""}
                </div>
                {row.purge_reason && <p className="text-slate-700">사유: {row.purge_reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
