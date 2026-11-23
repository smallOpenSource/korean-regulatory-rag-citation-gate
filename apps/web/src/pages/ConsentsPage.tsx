/**
 * ConsentsPage — Wave-Audit-Defect-Fix C1 (plan §6 line 366)
 *
 * 동의 관리 (신용정보법 §32, T214 / T229) UI. Surfaces 5 backend endpoints:
 *   - GET    /consents/customer/{customer_id}    (customer view)
 *   - POST   /consents/grant                    → consent_recorded
 *   - POST   /consents/withdraw                 → consent_withdrawn / dynamic
 *   - POST   /consents/marketing/stop           → marketing_consent_withdrawn
 *   - POST   /consents/general-bundle           → general_bundle_consent
 *
 * Backend canonical codes already present in core/audit.py:64-71 — no
 * migration needed. info_access_requested / info_access_responded endpoints
 * (262, 299) carry to a follow-up; this page targets the 4-form click-through
 * the plan acceptance enumerates.
 *
 * Role gate: PB / WM front-office submit; ADMIN + AUDIT_VIEWER can read.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badges";
import { getResource, postResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import { useAuthStore } from "../store/auth";

type ConsentType =
  | "GENERAL_BUNDLE"
  | "INFORMATION_USE"
  | "MARKETING_CONTACT"
  | "DATA_SHARING_THIRD_PARTY";

const CONSENT_TYPE_LABEL: Record<ConsentType, string> = {
  GENERAL_BUNDLE: "일괄동의 (§32 + §40)",
  INFORMATION_USE: "정보이용동의",
  MARKETING_CONTACT: "마케팅 연락동의",
  DATA_SHARING_THIRD_PARTY: "제3자 정보제공",
};

interface ConsentRow {
  id: string;
  customer_id: string;
  consent_type: string;
  consent_scope: Record<string, unknown>;
  granted_at: string | null;
  withdrawn_at: string | null;
  employee_id: string | null;
}

interface CustomerConsentsResponse {
  customer_id: string;
  consents: ConsentRow[];
  synthetic: boolean;
}

const WRITE_ROLES = new Set(["PB", "WM"]);

export function ConsentsPage() {
  const user = useAuthStore((s) => s.user);
  const roleCode = user?.roleCode ?? "";
  const canSubmit = WRITE_ROLES.has(roleCode);
  const queryClient = useQueryClient();

  const [customerId, setCustomerId] = useState("");
  const [grantType, setGrantType] = useState<ConsentType>("INFORMATION_USE");
  const [error, setError] = useState<string | null>(null);

  const customerView = useQuery<CustomerConsentsResponse>({
    queryKey: ["consents", "customer", customerId],
    queryFn: () =>
      getResource<CustomerConsentsResponse>(
        `/consents/customer/${encodeURIComponent(customerId)}`,
      ),
    enabled: customerId.trim().length > 0,
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["consents", "customer", customerId] });
  }

  const grantMutation = useMutation<ConsentRow, Error, void>({
    mutationFn: () =>
      postResource<ConsentRow>("/consents/grant", {
        customer_id: customerId.trim(),
        consent_type: grantType,
        consent_scope: {},
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err.message),
  });

  const withdrawMutation = useMutation<ConsentRow, Error, ConsentType>({
    mutationFn: (consentType) =>
      postResource<ConsentRow>("/consents/withdraw", {
        customer_id: customerId.trim(),
        consent_type: consentType,
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err.message),
  });

  const marketingStopMutation = useMutation<ConsentRow, Error, void>({
    mutationFn: () =>
      postResource<ConsentRow>("/consents/marketing/stop", {
        customer_id: customerId.trim(),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err.message),
  });

  const bundleMutation = useMutation<ConsentRow, Error, void>({
    mutationFn: () =>
      postResource<ConsentRow>("/consents/general-bundle", {
        customer_id: customerId.trim(),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err.message),
  });

  function requireCustomerId(): boolean {
    if (!customerId.trim()) {
      setError("customer_id를 먼저 입력하십시오");
      return false;
    }
    return true;
  }

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-indigo-700 to-blue-700 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-indigo-100">
          Customer Consents
        </p>
        <h1 className="mt-3 text-3xl font-black">개인·신용정보 동의 관리</h1>
        <p className="mt-2 text-indigo-50 text-sm">
          신용정보법 §32 (정보 이용·제공동의) + §40 (마케팅) + KFC §44 일괄동의.
          PB / WM 만 등록/철회할 수 있으며 모든 변경은 audit_logs에 즉시 박제됩니다.
        </p>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-900">고객 선택</h2>
        <label className="mt-3 grid gap-1 text-sm">
          <span className="font-semibold text-slate-700">customer_id (UUID)</span>
          <input
            type="text"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="UUID"
          />
        </label>
        {error && (
          <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {error}
          </p>
        )}
      </section>

      {canSubmit && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-bold text-slate-900">동의 등록/철회</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-semibold text-slate-800">개별 동의 등록</h3>
              <label className="mt-2 grid gap-1 text-sm">
                <span className="font-semibold text-slate-700">동의 유형</span>
                <select
                  value={grantType}
                  onChange={(e) => setGrantType(e.target.value as ConsentType)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  {(Object.keys(CONSENT_TYPE_LABEL) as ConsentType[]).map((t) => (
                    <option key={t} value={t}>
                      {CONSENT_TYPE_LABEL[t]}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => requireCustomerId() && grantMutation.mutate()}
                disabled={grantMutation.isPending}
                className="mt-3 rounded-xl border border-blue-300 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800 hover:bg-blue-100 disabled:opacity-50"
              >
                동의 등록
              </button>
              <button
                type="button"
                onClick={() => requireCustomerId() && withdrawMutation.mutate(grantType)}
                disabled={withdrawMutation.isPending}
                className="ml-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
              >
                동의 철회
              </button>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-semibold text-slate-800">일괄/마케팅</h3>
              <button
                type="button"
                onClick={() => requireCustomerId() && bundleMutation.mutate()}
                disabled={bundleMutation.isPending}
                className="rounded-xl border border-indigo-300 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-800 hover:bg-indigo-100 disabled:opacity-50"
              >
                일괄동의 발급 (§32+§40)
              </button>
              <button
                type="button"
                onClick={() => requireCustomerId() && marketingStopMutation.mutate()}
                disabled={marketingStopMutation.isPending}
                className="ml-2 rounded-xl border border-rose-300 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-800 hover:bg-rose-100 disabled:opacity-50"
              >
                마케팅 수신 중단
              </button>
            </div>
          </div>
        </section>
      )}

      {customerId.trim() && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-900">고객 동의 상태</h2>
            {customerView.data?.synthetic && (
              <Badge tone="orange">합성 데이터</Badge>
            )}
          </div>
          {customerView.isPending && (
            <p className="mt-3 text-xs text-slate-500">로드 중...</p>
          )}
          {customerView.isError && (
            <p className="mt-3 text-xs text-rose-700">
              조회 실패: {customerView.error.message}
            </p>
          )}
          {customerView.data && customerView.data.consents.length === 0 && (
            <p className="mt-3 text-xs text-slate-500">등록된 동의 없음</p>
          )}
          {customerView.data && customerView.data.consents.length > 0 && (
            <ul className="mt-3 grid gap-2" role="list">
              {customerView.data.consents.map((c) => (
                <li
                  key={c.id}
                  className="grid gap-1 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="rounded bg-white px-2 py-0.5 font-bold text-slate-600">
                      {c.id.slice(0, 8)}
                    </code>
                    <Badge tone={c.withdrawn_at ? "gray" : "green"}>
                      {CONSENT_TYPE_LABEL[c.consent_type as ConsentType] ??
                        c.consent_type}
                    </Badge>
                    {c.withdrawn_at && <Badge tone="red">철회</Badge>}
                  </div>
                  <div className="text-slate-500">
                    등록: {formatBankerTimestamp(c.granted_at)}
                    {c.withdrawn_at && (
                      <> · 철회: {formatBankerTimestamp(c.withdrawn_at)}</>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
