/**
 * Center pane of ConsultationPage — AI briefing, compliance checklist, notes,
 * and the complete-consultation action.
 * Extracted during Stage 2 T28 split (DEV-02). Behavior unchanged.
 */
import { AIMetadataFooter } from "./AIMetadataFooter";
import { KO } from "../lib/i18n";
import { consultationCanComplete } from "../lib/compliance";

export function ConsultationWorkspacePane({
  consultationId,
  suitabilityChecked,
  explanationChecked,
  onSuitabilityChange,
  onExplanationChange,
  onComplete,
  briefingOutputId,
  onGenerateBriefing,
  isGenerating,
}: {
  consultationId: string;
  suitabilityChecked: boolean;
  explanationChecked: boolean;
  onSuitabilityChange: (v: boolean) => void;
  onExplanationChange: (v: boolean) => void;
  onComplete: () => void;
  briefingOutputId: string | null;
  onGenerateBriefing: () => void;
  isGenerating: boolean;
}) {
  const canComplete = consultationCanComplete(suitabilityChecked, explanationChecked);

  return (
    <div className="grid gap-3 px-1">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-900">{KO.consultation.aiBriefing}</h2>
          {consultationId !== "new" && (
            <button
              type="button"
              onClick={onGenerateBriefing}
              disabled={isGenerating}
              className="rounded-xl bg-blue-700 px-3 py-1.5 text-xs font-bold text-white disabled:bg-slate-300 disabled:text-slate-500"
            >
              {isGenerating ? KO.consultation.briefingPending : KO.consultation.generateBriefing}
            </button>
          )}
        </div>
        <p className="mt-2 text-sm text-slate-600">
          AI 브리핑은 고객 포트폴리오와 하우스뷰를 기반으로 생성됩니다. 생성 결과는
          참고용이며 PB/WM의 최종 판단을 대체하지 않습니다.
        </p>
        {briefingOutputId && <AIMetadataFooter ai_output_id={briefingOutputId} />}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">준법 체크리스트</h2>
        <div className="mt-3 grid gap-2">
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium hover:bg-slate-50">
            <input
              type="checkbox"
              checked={suitabilityChecked}
              onChange={(e) => onSuitabilityChange(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-blue-700"
            />
            {KO.consultation.suitabilityChecked}
          </label>
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium hover:bg-slate-50">
            <input
              type="checkbox"
              checked={explanationChecked}
              onChange={(e) => onExplanationChange(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-blue-700"
            />
            {KO.consultation.explanationChecked}
          </label>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-base font-semibold text-slate-900">{KO.consultation.workspace}</h2>
        <label className="grid gap-2 text-sm font-semibold text-slate-700">
          {KO.consultation.notes}
          <textarea
            className="min-h-36 rounded-xl border border-slate-300 p-3 text-sm font-normal text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            placeholder={KO.consultation.notesPlaceholder}
          />
        </label>
        <button
          type="button"
          disabled={!canComplete}
          onClick={onComplete}
          className="mt-4 rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
          title={canComplete ? undefined : KO.consultation.completePending}
        >
          {KO.consultation.complete}
        </button>
      </section>
    </div>
  );
}
