/**
 * AIFinalApprovalBadge (T231, REG-02 §5 보조수단성)
 *
 * Renders the dual-state badge on every customer-facing AI output surface.
 * Source of truth is ai_outputs.employee_final_approval (V039 column).
 *
 * - Unapproved (default): `초안·검토용 — 보조수단성` (yellow)
 * - Approved:             `직원 최종 승인됨` (green)
 *
 * 7-agent contract: house_view_generation, consultation_briefing, nba_script,
 * email_draft, rag_qa, compliance_check, portfolio_analysis. Frontend MUST
 * place this badge on every page that displays output from any of the seven.
 */

import type { FC } from "react";

export interface AIFinalApprovalBadgeProps {
  employeeFinalApproval: boolean;
  approvedAt?: string | null;
  approvedBy?: string | null;
  agentId?: string;
}

export const AIFinalApprovalBadge: FC<AIFinalApprovalBadgeProps> = ({
  employeeFinalApproval,
  approvedAt,
  approvedBy,
  agentId,
}) => {
  if (employeeFinalApproval) {
    return (
      <span
        role="status"
        aria-label={`AI 출력 직원 최종 승인됨${agentId ? ` (에이전트 ${agentId})` : ""}`}
        className="inline-flex items-center gap-1 rounded-md bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 ring-1 ring-inset ring-green-600/20"
        data-testid="ai-final-approval-badge"
        data-state="approved"
      >
        직원 최종 승인됨
        {approvedAt ? <span className="ml-1 text-[0.65rem] opacity-70">{approvedAt.slice(0, 16).replace("T", " ")}</span> : null}
      </span>
    );
  }
  return (
    <span
      role="status"
      aria-label={`AI 출력 초안·검토용 — 보조수단성${agentId ? ` (에이전트 ${agentId})` : ""}`}
      className="inline-flex items-center gap-1 rounded-md bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 ring-1 ring-inset ring-yellow-600/20"
      data-testid="ai-final-approval-badge"
      data-state="draft"
    >
      초안·검토용 — 보조수단성
    </span>
  );
};

/** AI는 결정 지원 caveat copy (T276) — reused across 7 agent surfaces. */
export const AI_DECISION_SUPPORT_CAVEAT = "AI는 결정 지원이며 최종 책임은 담당 직원에게 있습니다.";

export const AIDecisionSupportCaveat: FC<{ agentId?: string }> = ({ agentId }) => (
  <p
    role="note"
    className="mt-1 text-[0.7rem] text-gray-600"
    data-testid="ai-decision-support-caveat"
    data-agent-id={agentId}
  >
    {AI_DECISION_SUPPORT_CAVEAT}
  </p>
);
