/**
 * MarketingReviewPage — Wave-Audit-Defect-Fix C4 (plan §6 line 369)
 *
 * 광고심의 게이트 UI: POST /marketing-review sends copy through the static
 * lint rules (단정문구/손실보전/이익보장) and the AI compliance_check gate.
 * Canonical codes (marketing_review_submitted / _approved / _rejected /
 * _blocked) pre-exist in core/audit.py:94-97 — no new migration.
 *
 * Role gate: PB / WM staff submit drafts; ADMIN reviews; AUDIT_VIEWER can
 * see history (the page itself is read-only for that role).
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Badge } from "../components/Badges";
import { postResource } from "../lib/api";
import { useAuthStore } from "../store/auth";

type MarketingDecision = "MARKETING_REVIEW_PASS" | "MARKETING_REVIEW_BLOCK";

interface MarketingReviewResponse {
  decision: MarketingDecision;
  classification: string;
  issue_codes: string[];
  ai_reasoning: string | null;
  consultation_id: string | null;
}

interface MarketingReviewRequest {
  subject: string;
  body: string;
  marketing_classified: boolean;
  pre_review_number?: string;
  consultation_id?: string;
}

const WRITE_ROLES = new Set(["PB", "WM", "ADMIN"]);

export function MarketingReviewPage() {
  const user = useAuthStore((s) => s.user);
  const roleCode = user?.roleCode ?? "";
  const canSubmit = WRITE_ROLES.has(roleCode);

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [marketingClassified, setMarketingClassified] = useState(false);
  const [preReviewNumber, setPreReviewNumber] = useState("");
  const [consultationId, setConsultationId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submitMutation = useMutation<MarketingReviewResponse, Error, MarketingReviewRequest>({
    mutationFn: (req) => postResource<MarketingReviewResponse>("/marketing-review", req),
    onError: (err) => setError(err.message),
    onSuccess: () => setError(null),
  });

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!body.trim()) {
      setError("광고 문안(body)을 입력하십시오");
      return;
    }
    submitMutation.mutate({
      subject: subject.trim(),
      body: body.trim(),
      marketing_classified: marketingClassified,
      pre_review_number: preReviewNumber.trim() || undefined,
      consultation_id: consultationId.trim() || undefined,
    });
  }

  const result = submitMutation.data;
  const isBlocked = result?.decision === "MARKETING_REVIEW_BLOCK";

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-violet-700 to-fuchsia-700 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-violet-100">
          광고문안 심의
        </p>
        <h1 className="mt-3 text-3xl font-black">Marketing Review</h1>
        <p className="mt-2 text-violet-50 text-sm">
          금융소비자보호법 §광고규제 + 자본시장법 §광고심의. 단정문구·손실보전·이익보장
          정적 점검 + AI 컴플라이언스 게이트를 통과한 문안만 발송할 수 있습니다.
        </p>
      </section>

      {canSubmit ? (
        <section
          aria-labelledby="marketing-review-form"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2 id="marketing-review-form" className="text-base font-bold text-slate-900">
            광고 문안 심의 요청
          </h2>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">제목</span>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="발송 제목"
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="font-semibold text-slate-700">본문 (필수)</span>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={6}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                aria-required="true"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-semibold text-slate-700">
                  사전심의 번호 (해당 시)
                </span>
                <input
                  type="text"
                  value={preReviewNumber}
                  onChange={(e) => setPreReviewNumber(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="예: PRE-2026-0042"
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-semibold text-slate-700">상담 ID (선택)</span>
                <input
                  type="text"
                  value={consultationId}
                  onChange={(e) => setConsultationId(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  placeholder="UUID — gate 결과를 consultation에 반영"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={marketingClassified}
                onChange={(e) => setMarketingClassified(e.target.checked)}
                className="h-4 w-4 rounded border-slate-400"
              />
              <span className="font-semibold text-violet-700">
                광고로 분류됨 (광고심의 필수 대상)
              </span>
            </label>
            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={submitMutation.isPending}
              className="justify-self-start rounded-xl border border-violet-300 bg-violet-50 px-4 py-2 text-sm font-semibold text-violet-800 hover:bg-violet-100 disabled:opacity-50"
            >
              {submitMutation.isPending ? "심의 중..." : "심의 요청"}
            </button>
          </form>
        </section>
      ) : (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
          광고 심의 요청은 PB / WM / ADMIN 만 가능합니다. (현재 역할:{" "}
          {roleCode || "미인증"})
        </section>
      )}

      {result && (
        <section
          aria-labelledby="marketing-review-result"
          className={`rounded-2xl border p-6 shadow-sm ${
            isBlocked
              ? "border-rose-300 bg-rose-50"
              : "border-emerald-300 bg-emerald-50"
          }`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="marketing-review-result" className="text-base font-bold text-slate-900">
              심의 결과
            </h2>
            <Badge tone={isBlocked ? "red" : "green"}>
              {isBlocked ? "차단 (BLOCK)" : "승인 (PASS)"}
            </Badge>
          </div>
          <dl className="mt-3 grid gap-2 text-xs text-slate-700">
            <div className="grid grid-cols-[max-content_1fr] gap-2">
              <dt className="font-semibold">분류</dt>
              <dd>{result.classification}</dd>
            </div>
            {result.issue_codes.length > 0 && (
              <div className="grid grid-cols-[max-content_1fr] gap-2">
                <dt className="font-semibold">위반 코드</dt>
                <dd>
                  <ul className="grid gap-1" role="list">
                    {result.issue_codes.map((code) => (
                      <li key={code} className="rounded bg-white px-2 py-0.5 font-mono">
                        {code}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
            {result.ai_reasoning && (
              <div className="grid gap-1">
                <dt className="font-semibold">AI 판단 사유 (redacted)</dt>
                <dd className="whitespace-pre-wrap rounded bg-white p-2">
                  {result.ai_reasoning}
                </dd>
              </div>
            )}
            {result.consultation_id && (
              <div className="grid grid-cols-[max-content_1fr] gap-2">
                <dt className="font-semibold">상담 게이트 반영</dt>
                <dd>{result.consultation_id}</dd>
              </div>
            )}
          </dl>
        </section>
      )}
    </div>
  );
}
