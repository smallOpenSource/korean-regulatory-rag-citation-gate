/**
 * RAG Q&A Chat — AI 이중 격리 통제 (서버 측 분류 + 인용 검증)
 * Chat-style interface, POST /rag/qa, inline clickable citations,
 * fail_closed_reason_code visual cue, token consumption indicator.
 */
import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Badge, StatusBadge } from "../components/Badges";
import { DevReference } from "../components/DevReference";
import { postResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RagCitation {
  chunk_id?: string;
  document_title?: string;
  source_type_code?: string;
  source_url?: string;
  published_at?: string;
  chunk_no?: number;
  quote?: string;
}

interface BlockedCaveat {
  status?: string;
  reason?: string;
  fail_closed_reason_code?: string;
  grounding_required?: boolean;
}

interface RagResponse {
  status_code: string;
  answer: string;
  // ADR-009 §G1 per-trace root cause + ralplan v4 C3: the framing
  // disclaimer + question echo were previously bundled into `answer`,
  // dragging the RAGAS Faithfulness per-trace pass rate because the
  // meta-statements were structurally un-entailed by any source chunk.
  // Backend now emits them in a separate field so the UI renders both
  // and RAGAS scores only the citation-derived body.
  attribution_note?: string;
  confidence?: number;
  caveat?: string | BlockedCaveat;
  citations?: RagCitation[];
  output_id?: string;
  generated_at?: string;
  model_name?: string;
  readiness?: { status_code: string; embedded_chunk_count: number; pending_raw_document_count: number; message: string };
}

interface ChatMessage {
  id: string;
  question: string;
  response: RagResponse;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FAIL_CLOSED_LABELS: Record<string, string> = {
  NO_CITATION: "근거 없음 (NO_CITATION)",
  SOURCE_MISMATCH: "출처 불일치 (SOURCE_MISMATCH)",
  EMPTY_SANITIZED_TEXT: "청크 텍스트 없음 (EMPTY_SANITIZED_TEXT)",
  UNSUPPORTED_FILTER: "지원되지 않는 필터 (UNSUPPORTED_FILTER)",
  QUARANTINED_CONTEXT: "격리된 문서 컨텍스트 (QUARANTINED_CONTEXT)",
  DIMENSION_MISMATCH: "벡터 차원 불일치 (DIMENSION_MISMATCH)",
  LOW_FAITHFULNESS: "근거 신뢰도 부족 (LOW_FAITHFULNESS)",
  PROMPT_INJECTION_DETECTED: "프롬프트 인젝션 탐지 (PROMPT_INJECTION_DETECTED)",
  CONTENT_SAFETY_BLOCKED: "콘텐츠 안전 차단 (CONTENT_SAFETY_BLOCKED)",
};

function getFailClosedCode(caveat: RagResponse["caveat"]): string | undefined {
  if (!caveat || typeof caveat === "string") return undefined;
  return caveat.fail_closed_reason_code;
}

function getFailClosedReason(caveat: RagResponse["caveat"]): string {
  if (!caveat) return "";
  if (typeof caveat === "string") return caveat;
  return caveat.reason ?? "";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FailClosedBanner({ caveat }: { caveat: RagResponse["caveat"] }) {
  const code = getFailClosedCode(caveat);
  const reason = getFailClosedReason(caveat);
  if (!code) return null;

  return (
    <div
      role="alert"
      className="mt-3 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3"
    >
      <svg className="mt-0.5 size-4 shrink-0 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
      <div>
        <p className="text-sm font-bold text-red-700">
          Fail-Closed: {FAIL_CLOSED_LABELS[code] ?? code}
        </p>
        {reason && <p className="mt-0.5 text-xs text-red-600">{reason}</p>}
        <p className="mt-1 text-xs text-red-500">
          시스템 정책에 따라 근거 없는 답변은 자동으로 차단됩니다.
          <DevReference inline="ADR-005" />
        </p>
      </div>
    </div>
  );
}

function CitationList({ citations }: { citations: RagCitation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="mb-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">인용 출처</p>
      <ol className="space-y-1.5">
        {citations.map((c, idx) => (
          <li key={c.chunk_id ?? idx} className="flex items-start gap-2">
            <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded bg-blue-100 text-xs font-bold text-blue-700">
              {idx + 1}
            </span>
            <div className="min-w-0">
              {c.source_url ? (
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-semibold text-blue-700 hover:underline"
                >
                  {c.document_title ?? c.source_url}
                </a>
              ) : (
                <span className="text-sm font-semibold text-slate-700">
                  {c.document_title ?? `청크 #${c.chunk_no ?? idx + 1}`}
                </span>
              )}
              {c.source_type_code && (
                <span className="ml-1.5 text-xs text-slate-400">[{c.source_type_code}]</span>
              )}
              {c.published_at && (
                <span className="ml-1.5 text-xs text-slate-400">{c.published_at.slice(0, 10)}</span>
              )}
              {c.quote && (
                <p className="mt-0.5 rounded bg-slate-50 px-2 py-1 text-xs italic text-slate-600 line-clamp-2">
                  "{c.quote}"
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function TokenIndicator({ response }: { response: RagResponse }) {
  if (!response.model_name && !response.output_id) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3 text-xs text-slate-400">
      {response.model_name && (
        <span>
          모델: <span className="font-mono text-slate-600">{response.model_name}</span>
        </span>
      )}
      {response.confidence !== undefined && (
        <span>
          신뢰도:{" "}
          <span className={`font-semibold ${response.confidence >= 0.7 ? "text-emerald-600" : response.confidence >= 0.5 ? "text-amber-600" : "text-red-600"}`}>
            {(response.confidence * 100).toFixed(0)}%
          </span>
        </span>
      )}
      {response.output_id && (
        <span>
          AI 출력 ID: <span className="font-mono text-slate-500">{response.output_id.slice(0, 8)}…</span>
        </span>
      )}
    </div>
  );
}

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isBlocked = msg.response.status_code === "BLOCKED";
  return (
    <div className="space-y-3">
      {/* User question */}
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-blue-700 px-4 py-3 text-sm text-white">
          {msg.question}
        </div>
      </div>

      {/* AI answer */}
      <div className="flex justify-start">
        <div className={`max-w-[90%] rounded-2xl rounded-tl-sm border p-4 ${isBlocked ? "border-red-200 bg-red-50" : "border-slate-200 bg-white"}`}>
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">AI 응답</span>
            <StatusBadge statusCode={msg.response.status_code} />
          </div>

          {isBlocked ? (
            <>
              <p className="text-sm text-slate-600">근거 있는 청크가 검색되지 않아 답변이 차단되었습니다.</p>
              <FailClosedBanner caveat={msg.response.caveat} />
            </>
          ) : (
            <>
              {msg.response.attribution_note && (
                <p className="mb-2 text-xs italic text-slate-500">
                  {msg.response.attribution_note}
                </p>
              )}
              <p className="text-sm leading-relaxed text-slate-800">{msg.response.answer}</p>
              <CitationList citations={msg.response.citations ?? []} />
            </>
          )}

          <TokenIndicator response={msg.response} />

          <p className="mt-2 text-right text-xs text-slate-400">
            {msg.response.generated_at ? formatBankerTimestamp(msg.response.generated_at) : msg.timestamp}
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

let msgCounter = 0;

export function RagPage() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const ragMutation = useMutation({
    mutationFn: (q: string) =>
      postResource<RagResponse>("/rag/qa", {
        question: q,
        filter_source_types: ["DART", "REG_PAGE", "RESEARCH", "MANUAL"],
      }),
    onSuccess: (data, q) => {
      msgCounter += 1;
      setHistory((prev) => [
        ...prev,
        {
          id: `msg-${msgCounter}`,
          question: q,
          response: data,
          timestamp: new Date().toLocaleTimeString("ko-KR"),
        },
      ]);
      setQuestion("");
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || ragMutation.isPending) return;
    ragMutation.mutate(q);
  };

  return (
    <section className="flex h-[calc(100vh-10rem)] flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h1 className="text-xl font-black text-slate-950">RAG Q&amp;A</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            상품·규정 질문 → 승인된 청크 기반 근거 답변 · AI 이중 격리 적용
            <DevReference inline="W2-T1/W3-T6 dual-LLM" />
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="blue">인용 게이트</Badge>
          <Badge tone="orange">근거 미충족 시 자동 차단</Badge>
        </div>
      </div>

      {/* Chat history */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {history.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="rounded-2xl bg-slate-50 p-6">
              <p className="text-sm font-semibold text-slate-700">아직 질문이 없습니다.</p>
              <p className="mt-1 text-xs text-slate-500">
                ELS 녹인, 만기 설명의무, 규정 해석 등 검색 기반 질문을 입력하세요.
              </p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                {["ELS knock-in 후 설명의무 범위", "사모펀드 투자 적합성 기준", "금융투자업 규정 §4-20"].map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setQuestion(s)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:border-blue-300 hover:text-blue-700"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {history.map((msg) => (
          <ChatBubble key={msg.id} msg={msg} />
        ))}
        {ragMutation.isPending && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3">
              <span className="flex items-center gap-2 text-sm text-slate-400">
                <span className="inline-flex gap-1">
                  <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:0ms]" />
                  <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
                  <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]" />
                </span>
                AI가 검색 중입니다…
              </span>
            </div>
          </div>
        )}
        {ragMutation.error && (
          <div role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
            요청 처리 중 오류가 발생했습니다: {ragMutation.error.message}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-slate-200 px-5 py-4"
      >
        <div className="flex gap-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e as unknown as React.FormEvent);
              }
            }}
            placeholder="ELS knock-in 후 고객 설명의무 범위 (Shift+Enter: 줄바꿈)"
            rows={2}
            className="flex-1 resize-none rounded-xl border border-slate-300 p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="RAG 질문 입력"
          />
          <button
            type="submit"
            disabled={ragMutation.isPending || !question.trim()}
            className="self-end rounded-xl bg-blue-700 px-4 py-3 text-sm font-bold text-white hover:bg-blue-800 disabled:opacity-50"
            aria-label="질문 전송"
          >
            <svg className="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          답변은 승인된 RAG 청크만 사용 · 근거 없으면 자동 차단
          <DevReference inline="ADR-005 Fail-Closed" />
        </p>
      </form>
    </section>
  );
}
