/**
 * AIMetadataFooter — REG-03 T255
 *
 * Renders the 4-tuple AI provenance row beneath every AI-generated card:
 *   {generated_at, model, confidence, source}
 *
 * Fetches the ai_outputs row by ID.  Shows a synthetic data watermark when
 * the output carries synthetic:true in its output_json payload.
 *
 * Usage:
 *   <AIMetadataFooter ai_output_id="uuid-from-api" />
 */

import { useQuery } from "@tanstack/react-query";
import { getResource } from "../lib/api";
import { formatBankerTimestamp } from "../lib/format";
import { KO } from "../lib/i18n";

// ─── Types ───────────────────────────────────────────────────────────────────

interface AiOutputRow {
  id: string;
  generated_at: string;
  model_name: string;
  output_json?: {
    confidence?: number;
    source?: string;
    synthetic?: boolean;
    status?: string;
    grounding_required?: boolean;
    // P0 HITL quality signals — surfaced so a PB/WM reviewer sees data-quality
    // disclosure, grounding fidelity, and PII masking before acting on the
    // output (portfolio_analysis / consultation_briefing / nba_script).
    data_quality_notice?: string;
    faithfulness?: {
      method?: string;
      has_disclosure?: boolean;
      ungrounded_figures?: string[];
      flags?: string[];
      passed?: boolean;
    };
    _pii_masked_categories?: string[];
  };
}

interface AIMetadataFooterProps {
  ai_output_id: string;
  /** Extra Tailwind classes applied to the outer container. */
  className?: string;
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function MetaTuple({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex gap-1">
      <span className="font-semibold text-slate-500">{label}:</span>
      <span className="text-slate-700">{value}</span>
    </span>
  );
}

function faithfulnessFlagLabel(flag: string): string {
  if (flag === "MISSING_DATA_QUALITY_DISCLOSURE") return KO.ai.faithfulnessMissingDisclosure;
  if (flag === "UNGROUNDED_FIGURES") return KO.ai.faithfulnessUngroundedFigures;
  return flag;
}

// ─── Main component ──────────────────────────────────────────────────────────

export function AIMetadataFooter({ ai_output_id, className = "" }: AIMetadataFooterProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-output", ai_output_id],
    queryFn: () => getResource<AiOutputRow>(`/ai-outputs/${ai_output_id}`),
    enabled: Boolean(ai_output_id),
    staleTime: 60_000,
  });

  if (!ai_output_id) {
    return null;
  }

  if (isLoading) {
    return (
      <div
        className={`mt-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 ${className}`}
        aria-label={KO.ai.aiMetadata}
      >
        <p className="text-xs text-slate-400">{KO.ai.loading}</p>
      </div>
    );
  }

  if (isError || !data) {
    return null;
  }

  const isSynthetic = Boolean(data.output_json?.synthetic);
  const confidence = data.output_json?.confidence;
  const source = data.output_json?.source ?? data.output_json?.status ?? "AI 생성";

  const generatedAtFormatted = formatBankerTimestamp(data.generated_at);

  const confidencePct =
    confidence !== undefined && confidence !== null
      ? `${Math.round(confidence * 100)}%`
      : null;

  const dataQualityNotice = data.output_json?.data_quality_notice;
  const faithfulness = data.output_json?.faithfulness;
  const piiMasked = data.output_json?._pii_masked_categories ?? [];
  const ungroundedFigures = faithfulness?.ungrounded_figures ?? [];
  const faithfulnessFlags = faithfulness?.flags ?? [];

  return (
    <div
      className={`mt-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 ${className}`}
      role="note"
      aria-label={KO.ai.aiMetadata}
    >
      {isSynthetic && (
        <div
          className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-bold text-amber-800"
          role="alert"
          aria-live="polite"
        >
          {KO.ai.syntheticWatermark}
        </div>
      )}
      {dataQualityNotice && (
        <div
          className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900"
          role="note"
          data-testid="ai-data-quality-notice"
        >
          <span className="font-bold">{KO.ai.dataQualityNotice}: </span>
          <span>{dataQualityNotice}</span>
        </div>
      )}
      {faithfulness && (
        <div
          className="mb-2 flex flex-wrap items-center gap-1.5 text-xs"
          data-testid="ai-faithfulness"
        >
          <span
            className={`rounded-full px-2 py-0.5 font-bold ${
              faithfulness.passed
                ? "bg-emerald-100 text-emerald-800"
                : "bg-amber-100 text-amber-800"
            }`}
          >
            {KO.ai.faithfulness}:{" "}
            {faithfulness.passed ? KO.ai.faithfulnessOk : KO.ai.faithfulnessReview}
          </span>
          {faithfulnessFlags.map((flag) => (
            <span
              key={flag}
              className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-amber-800"
            >
              {faithfulnessFlagLabel(flag)}
            </span>
          ))}
          {ungroundedFigures.length > 0 && (
            <span className="text-amber-700">({ungroundedFigures.join(", ")})</span>
          )}
        </div>
      )}
      {piiMasked.length > 0 && (
        <div className="mb-2 text-xs text-slate-500" data-testid="ai-pii-masked">
          {KO.ai.piiMasked}: {piiMasked.join(", ")}
        </div>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <MetaTuple label={KO.ai.generatedAt} value={generatedAtFormatted} />
        <MetaTuple label={KO.ai.model} value={data.model_name} />
        {confidencePct !== null && (
          <MetaTuple label={KO.ai.confidence} value={confidencePct} />
        )}
        <MetaTuple label={KO.ai.source} value={source} />
      </div>
    </div>
  );
}
