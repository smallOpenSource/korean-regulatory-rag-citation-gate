import type { RecommendationGateState } from "../lib/types";

const CHECKS: Array<{ key: keyof RecommendationGateState; label: string }> = [
  { key: "suitabilityPassed", label: "적합성 원칙 확인" },
  { key: "explanationChecked", label: "설명의무 확인" },
  { key: "simulatedCustomerConsented", label: "합성 고객 동의 확인" },
  { key: "employeeFinalApproved", label: "직원 최종 승인" },
];

export function ComplianceChecklist({ value, onChange }: { value: RecommendationGateState; onChange: (next: RecommendationGateState) => void }) {
  return (
    <div className="grid gap-3" aria-label="4-gate checklist">
      {CHECKS.map((check) => (
        <label key={check.key} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium text-slate-700">
          <input
            type="checkbox"
            checked={value[check.key]}
            onChange={(event) => onChange({ ...value, [check.key]: event.target.checked })}
            className="h-4 w-4 rounded border-slate-300"
          />
          {check.label}
        </label>
      ))}
    </div>
  );
}

