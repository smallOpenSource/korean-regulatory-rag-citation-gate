/**
 * Shared types + constants for ConsultationPage panes.
 * Extracted from ConsultationPage.tsx during Stage 2 T28 split (DEV-02 large
 * module containment) — exact semantics preserved.
 */
import { KO } from "../lib/i18n";
import type { SyntheticCustomerNotice } from "../lib/types";

export interface CustomerSummary {
  id: string;
  customer_name?: string;
  customer_no?: string;
  scenario_label?: string;
  segment_code?: string;
  risk_grade_code?: string;
  total_assets_krw?: number | string;
  synthetic_customer_notice?: SyntheticCustomerNotice;
}

export interface GateState {
  gate_name: string;
  // T3-3 (F15): DB SoT V023:43 CHECK (gate_status IN ('PENDING','PASSED',
  // 'BLOCKED','ACKNOWLEDGED')). ACKNOWLEDGED는 PASSED 이후 branch-manager가
  // acknowledge_gate endpoint 호출 시 transition되는 lifecycle 상태이므로
  // frontend type 누락 시 raw enum 노출 + tone/label 분기에서 default fallback
  // (yellow/PENDING)로 잘못 표현됨.
  gate_status: "PASSED" | "BLOCKED" | "PENDING" | "ACKNOWLEDGED";
  gate_acknowledged_at?: string | null;
}

export interface FourGateResult {
  consultation_id: string;
  all_passed: boolean;
  gates: GateState[];
}

export interface BriefingJob {
  job_id: string;
  status_code: string;
}

export const GATE_LABEL: Record<string, string> = {
  suitability: KO.gate.suitability,
  explanation: KO.gate.explanation,
  unfair_solicitation: KO.gate.unfairSolicitation,
  marketing: KO.gate.marketing,
};
