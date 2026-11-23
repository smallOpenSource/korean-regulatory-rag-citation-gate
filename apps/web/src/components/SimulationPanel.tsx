import { useState } from "react";

import { ComplianceChecklist } from "./ComplianceChecklist";
import { allRecommendationGatesPass } from "../lib/compliance";
import { SimulationNotice, StatusBadge } from "./Badges";
import type { RecommendationGateState } from "../lib/types";

const INITIAL_GATES: RecommendationGateState = {
  suitabilityPassed: false,
  explanationChecked: false,
  simulatedCustomerConsented: false,
  employeeFinalApproved: false,
};

export function SimulationPanel() {
  const [gates, setGates] = useState(INITIAL_GATES);
  const statusCode = allRecommendationGatesPass(gates) ? "APPROVED" : "BLOCKED";

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="simulation-title">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="simulation-title" className="text-lg font-semibold text-slate-950">추천/주문 시뮬레이션</h2>
          <p className="text-sm text-slate-600">실제 주문 API 호출 없이 직원 화면 내 승인 조건을 점검합니다.</p>
        </div>
        <SimulationNotice />
      </div>
      <ComplianceChecklist value={gates} onChange={setGates} />
      <div className="mt-4 flex items-center justify-between rounded-xl bg-slate-50 p-4">
        <span className="text-sm font-medium text-slate-700">4-gate 평가 결과</span>
        <StatusBadge statusCode={statusCode} />
      </div>
    </section>
  );
}
