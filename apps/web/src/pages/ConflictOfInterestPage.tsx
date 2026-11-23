/**
 * ConflictOfInterestPage — Wave-Audit-Defect-Fix C3 (plan §6 line 368)
 *
 * Conflict-of-interest pre-disclosure UI surfacing 4 backend endpoints from
 * apps/api/harness/api/routers/conflict_of_interest.py:
 *   - GET    /conflict-disclosures             (list)
 *   - GET    /conflict-disclosures/{id}        (detail)
 *   - POST   /conflict-disclosures             (create — emits canonical
 *                                                conflict_disclosed OR
 *                                                conflict_of_interest_blocked
 *                                                per OQ-2; canonical pre-exists
 *                                                in core/audit.py:62-63, no new
 *                                                migration needed)
 *   - GET    /conflict-disclosures/check       (precheck for downstream gating)
 *
 * Role gate mirrors the backend: PB / WM / ADMIN / BRANCH_MANAGER can create;
 * AUDIT_VIEWER is read-only (list+detail only).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../components/Badges";
import { getResource, postResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import { useAuthStore } from "../store/auth";

type DisclosureType = "PRE_TRADE" | "POST_TRADE" | "RELATED_PARTY";

interface ConflictDisclosureRow {
  id: string;
  employee_id: string;
  customer_id: string;
  disclosure_type: DisclosureType;
  description_redacted: string | null;
  chinese_wall_violation: boolean;
  created_at: string;
  blocked_at: string | null;
}

interface ListResponse {
  items: ConflictDisclosureRow[];
  total: number;
}

interface CreatePayload {
  customer_id: string;
  disclosure_type: DisclosureType;
  description: string;
  chinese_wall_violation: boolean;
}

const DISCLOSURE_TYPE_LABEL: Record<DisclosureType, string> = {
  PRE_TRADE: "사전 거래 (Pre-Trade)",
  POST_TRADE: "사후 거래 (Post-Trade)",
  RELATED_PARTY: "특수관계인 거래 (Related Party)",
};

const WRITE_ROLES = new Set(["PB", "WM", "ADMIN", "BRANCH_MANAGER"]);

export function ConflictOfInterestPage() {
  const user = useAuthStore((s) => s.user);
  const roleCode = user?.roleCode ?? "";
  const canMutate = WRITE_ROLES.has(roleCode);
  const queryClient = useQueryClient();

  const listQuery = useQuery<ListResponse>({
    queryKey: ["conflict-disclosures"],
    queryFn: () => getResource<ListResponse>("/conflict-disclosures"),
  });

  const [customerId, setCustomerId] = useState("");
  const [disclosureType, setDisclosureType] = useState<DisclosureType>("PRE_TRADE");
  const [description, setDescription] = useState("");
  const [wallViolation, setWallViolation] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const createMutation = useMutation<ConflictDisclosureRow, Error, CreatePayload>({
    mutationFn: (body) =>
      postResource<ConflictDisclosureRow>("/conflict-disclosures", body),
    onSuccess: () => {
      setCustomerId("");
      setDescription("");
      setWallViolation(false);
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: ["conflict-disclosures"] });
    },
    onError: (err) => setFormError(err.message),
  });

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!customerId.trim()) {
      setFormError("customer_id를 입력하십시오");
      return;
    }
    createMutation.mutate({
      customer_id: customerId.trim(),
      disclosure_type: disclosureType,
      description: description.trim(),
      chinese_wall_violation: wallViolation,
    });
  }

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-amber-700 to-rose-700 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-amber-100">
          이해상충 사전공시
        </p>
        <h1 className="mt-3 text-3xl font-black">Conflict of Interest</h1>
        <p className="mt-2 text-amber-50 text-sm">
          자본시장법 §44 (이해상충 관리) 의무. 거래 전 사전공시 + Chinese Wall
          위반 차단 절차를 통해 고객 신뢰를 보호합니다.
        </p>
      </section>

      {canMutate && (
        <section
          aria-labelledby="conflict-disclose-form"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2 id="conflict-disclose-form" className="text-base font-bold text-slate-900">
            신규 이해상충 공시
          </h2>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">고객 ID</span>
              <input
                type="text"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                placeholder="UUID"
                aria-required="true"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">공시 유형</span>
              <select
                value={disclosureType}
                onChange={(e) => setDisclosureType(e.target.value as DisclosureType)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="PRE_TRADE">{DISCLOSURE_TYPE_LABEL.PRE_TRADE}</option>
                <option value="POST_TRADE">{DISCLOSURE_TYPE_LABEL.POST_TRADE}</option>
                <option value="RELATED_PARTY">
                  {DISCLOSURE_TYPE_LABEL.RELATED_PARTY}
                </option>
              </select>
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">상세 설명 (≤2000자)</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                maxLength={2000}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={wallViolation}
                onChange={(e) => setWallViolation(e.target.checked)}
                className="h-4 w-4 rounded border-slate-400 text-rose-600"
              />
              <span className="font-semibold text-rose-700">
                Chinese Wall 위반 (체결 차단)
              </span>
            </label>
            {formError && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {formError}
              </p>
            )}
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="justify-self-start rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
            >
              {createMutation.isPending ? "전송 중..." : "공시 등록"}
            </button>
          </form>
        </section>
      )}

      <section
        aria-labelledby="conflict-disclose-list"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2 id="conflict-disclose-list" className="text-base font-bold text-slate-900">
          이해상충 공시 목록
        </h2>
        {listQuery.isPending && (
          <p className="mt-3 text-xs text-slate-500">로드 중...</p>
        )}
        {listQuery.isError && (
          <p className="mt-3 text-xs text-rose-700">
            목록 로드 실패: {listQuery.error.message}
          </p>
        )}
        {listQuery.data && listQuery.data.items.length === 0 && (
          <p className="mt-3 text-xs text-slate-500">공시 기록 없음</p>
        )}
        {listQuery.data && listQuery.data.items.length > 0 && (
          <ul className="mt-3 grid gap-2" role="list">
            {listQuery.data.items.map((row) => (
              <li
                key={row.id}
                className="grid gap-1 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-white px-2 py-0.5 font-bold text-slate-600">
                    {row.id.slice(0, 8)}
                  </code>
                  <Badge tone={row.chinese_wall_violation ? "red" : "blue"}>
                    {DISCLOSURE_TYPE_LABEL[row.disclosure_type]}
                  </Badge>
                  {row.chinese_wall_violation && <Badge tone="red">차단</Badge>}
                </div>
                <div className="text-slate-500">
                  고객 {row.customer_id.slice(0, 8)} · 직원 {row.employee_id.slice(0, 8)}
                </div>
                <div className="text-slate-500">
                  공시: {formatBankerTimestamp(row.created_at)}
                  {row.blocked_at && (
                    <> · 차단: {formatBankerTimestamp(row.blocked_at)}</>
                  )}
                </div>
                {row.description_redacted && (
                  <p className="mt-1 text-slate-700">{row.description_redacted}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
