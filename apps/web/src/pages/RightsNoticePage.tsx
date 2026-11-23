/**
 * RightsNoticePage — T250
 *
 * Displays 4 customer rights (금융소비자보호법):
 *   1. 청약철회 7일/9일
 *   2. 위법계약해지 1년/5년
 *   3. 자료요구 30일
 *   4. 분쟁조정 30일
 *
 * Cancel / Acknowledge flow.
 * Triggered from consultation end.
 */

import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";

// Wave-Audit-Defect-Fix C6: real POST wiring (was stub setTimeout).
import { postResource } from "../lib/api";

interface Right {
  id: string;
  title: string;
  subtitle: string;
  period: string;
  description: string;
  note?: string;
}

const RIGHTS: Right[] = [
  {
    id: "withdrawal",
    title: "청약철회권",
    subtitle: "금융소비자보호법 제46조",
    period: "7일 / 9일 이내",
    description:
      "금융 상품 계약 체결 후 계약서류를 받은 날부터 7일(보험 9일) 이내에 청약을 철회할 수 있습니다. 위약금 또는 수수료 청구 불가.",
    note: "단, 보장개시일 이후 기간이 경과하였거나 청약을 완료한 날부터 30일이 경과하면 청약철회 불가.",
  },
  {
    id: "illegal_termination",
    title: "위법계약해지권",
    subtitle: "금융소비자보호법 제47조",
    period: "1년 이내 (계약일로부터 5년)",
    description:
      "금융회사가 6대 판매규제(적합성·적정성·설명의무·불공정영업·부당권유·광고규제)를 위반한 경우, 계약을 해지할 수 있습니다.",
    note: "해지요구일로부터 10일 이내에 금융회사가 수락 여부를 통지해야 합니다.",
  },
  {
    id: "data_request",
    title: "자료열람 요구권",
    subtitle: "금융소비자보호법 제28조",
    period: "요구 후 30일 이내",
    description:
      "금융 거래 관련 자료(상담·계약 관련 서류, AI 생성 문서 포함)의 열람·제공을 요구할 수 있습니다. 금융회사는 30일 이내에 응해야 합니다.",
    note: "정당한 사유 없이 거부 불가. AI 생성 문서의 경우 보조수단성 고지 포함.",
  },
  {
    id: "dispute",
    title: "분쟁조정 신청권",
    subtitle: "금융소비자보호법 제36조",
    period: "신청 후 30일 이내 처리",
    description:
      "금융 거래에서 분쟁 발생 시 금융감독원 금융분쟁조정위원회에 조정을 신청할 수 있습니다. 법원 소송 전 무료 분쟁 해결 절차입니다.",
    note: "분쟁조정 신청 중 금융회사는 소송 제기 불가 (특별 규정).",
  },
];

const TONE: Record<string, string> = {
  withdrawal: "border-blue-200 bg-blue-50",
  illegal_termination: "border-orange-200 bg-orange-50",
  data_request: "border-emerald-200 bg-emerald-50",
  dispute: "border-purple-200 bg-purple-50",
};

const PERIOD_TONE: Record<string, string> = {
  withdrawal: "border-blue-300 bg-blue-100 text-blue-800",
  illegal_termination: "border-orange-300 bg-orange-100 text-orange-800",
  data_request: "border-emerald-300 bg-emerald-100 text-emerald-800",
  dispute: "border-purple-300 bg-purple-100 text-purple-800",
};

interface AcknowledgeResponse {
  consultation_id: string;
  status: string;
}

export function RightsNoticePage() {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { consultationId?: string } };
  const consultationId = location.state?.consultationId ?? "";
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  // Wave-Audit-Defect-Fix C6: real POST to /rights-notice/acknowledge emits
  // canonical `rights_notice_acknowledged` audit row (V058). The earlier stub
  // setTimeout left no audit trail of PB acknowledgement.
  const ackMutation = useMutation<AcknowledgeResponse, Error, string>({
    mutationFn: (id: string) =>
      postResource<AcknowledgeResponse>("/rights-notice/acknowledge", {
        consultation_id: id,
      }),
    onSuccess: () => {
      setSubmitted(true);
      setTimeout(() => navigate(-1), 1500);
    },
  });

  function handleAcknowledge() {
    if (!acknowledged || !consultationId) return;
    ackMutation.mutate(consultationId);
  }

  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-blue-700 to-slate-800 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-blue-200">소비자 권리 고지</p>
        <h1 className="mt-3 text-3xl font-black">금융소비자 4대 권리 안내</h1>
        <p className="mt-2 text-blue-100 text-sm">
          금융소비자보호법에 따라 고객에게 다음 권리가 보장됩니다.
          상담 종료 전 반드시 안내하여 주십시오.
        </p>
      </section>

      {/* Rights Grid */}
      <div
        className="grid gap-4 md:grid-cols-2"
        role="list"
        aria-label="금융소비자 4대 권리 목록"
      >
        {RIGHTS.map((right) => (
          <article
            key={right.id}
            role="listitem"
            className={`rounded-2xl border p-5 ${TONE[right.id] ?? "border-slate-200 bg-slate-50"}`}
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-base font-black text-slate-950">{right.title}</h2>
                <p className="text-xs font-medium text-slate-500">{right.subtitle}</p>
              </div>
              <span
                className={`shrink-0 rounded-full border px-3 py-1 text-xs font-bold ${PERIOD_TONE[right.id] ?? "border-slate-300 bg-slate-100 text-slate-700"}`}
                aria-label={`적용 기간: ${right.period}`}
              >
                {right.period}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-800">{right.description}</p>
            {right.note && (
              <p className="mt-2.5 rounded-xl bg-white/70 p-2.5 text-xs text-slate-600">
                💡 {right.note}
              </p>
            )}
          </article>
        ))}
      </div>

      {/* Acknowledge Flow */}
      <section
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        aria-label="권리 고지 확인"
      >
        {submitted ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-800"
          >
            <span aria-hidden="true" className="text-xl">✅</span>
            <div>
              <p className="font-semibold">권리 고지 확인이 완료되었습니다.</p>
              <p className="text-sm text-emerald-700">이전 화면으로 돌아갑니다…</p>
            </div>
          </div>
        ) : (
          <div className="grid gap-4">
            <label
              htmlFor="rights-ack"
              className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 hover:border-blue-300 has-[:checked]:border-blue-600 has-[:checked]:bg-blue-50"
            >
              <input
                id="rights-ack"
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-blue-700"
                aria-label="위 4대 권리를 고객에게 충분히 안내하였음을 확인합니다"
              />
              <span className="text-sm font-medium text-slate-800">
                위 4대 권리를 고객에게 충분히 안내하였음을 확인합니다.
                <span className="block mt-1 text-xs text-slate-500">
                  이 확인은 감사 로그에 기록됩니다 (금융소비자보호법 제17조).
                </span>
              </span>
            </label>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
              >
                다음에 확인
              </button>
              <button
                type="button"
                onClick={handleAcknowledge}
                disabled={!acknowledged}
                aria-label="권리 고지 확인 완료"
                className="rounded-xl bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
              >
                확인 완료
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
