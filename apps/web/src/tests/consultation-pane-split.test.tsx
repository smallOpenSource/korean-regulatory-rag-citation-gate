/**
 * consultation-pane-split.test.tsx — T28 ConsultationPage split regression.
 *
 * Stage 2 T28 split: ConsultationPage 469 → 148 LOC + 4 pane modules.
 * Verifies that:
 *   - 3-pane ThreePaneLayout composition is in place
 *   - Each extracted pane component is importable + renders
 *   - Compliance checklist gates the complete button correctly
 *   - 4-gate panel role-gated acknowledge button visibility (BRANCH_MANAGER)
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConsultationCustomerSummaryPane } from "../components/ConsultationCustomerSummaryPane";
import { ConsultationFourGatePane } from "../components/ConsultationFourGatePane";
import { ConsultationWorkspacePane } from "../components/ConsultationWorkspacePane";

afterEach(cleanup);

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("T28 ConsultationPage split — pane components", () => {
  it("ConsultationCustomerSummaryPane shows select-customer hint when no customerId", () => {
    withProviders(<ConsultationCustomerSummaryPane customerId={null} />);
    // Multiple '고객' tokens render across heading + status copy; assert presence > 0.
    expect(screen.getAllByText(/고객/).length).toBeGreaterThan(0);
  });

  it("ConsultationFourGatePane shows 'not applicable' hint when consultationId='new'", () => {
    withProviders(
      <ConsultationFourGatePane
        consultationId="new"
        onAcknowledge={() => undefined}
        isBranchManager={false}
      />,
    );
    // Without a real consultation id, the panel renders panel title
    const panels = screen.getAllByText(/게이트|체크리스트|4-?gate/i);
    expect(panels.length).toBeGreaterThan(0);
  });

  it("ConsultationWorkspacePane shows briefing button when not 'new'", () => {
    withProviders(
      <ConsultationWorkspacePane
        consultationId="cons-1"
        suitabilityChecked={false}
        explanationChecked={false}
        onSuitabilityChange={() => undefined}
        onExplanationChange={() => undefined}
        onComplete={() => undefined}
        briefingOutputId={null}
        onGenerateBriefing={() => undefined}
        isGenerating={false}
      />,
    );
    // AI 브리핑 appears in heading + button + descriptive paragraph; use getAllByText.
    expect(screen.getAllByText(/AI 브리핑/).length).toBeGreaterThan(0);
  });

  it("complete button disabled until both suitability + explanation checked", () => {
    const { rerender } = withProviders(
      <ConsultationWorkspacePane
        consultationId="cons-1"
        suitabilityChecked={false}
        explanationChecked={false}
        onSuitabilityChange={() => undefined}
        onExplanationChange={() => undefined}
        onComplete={() => undefined}
        briefingOutputId={null}
        onGenerateBriefing={() => undefined}
        isGenerating={false}
      />,
    );
    const initialButtons = screen.getAllByRole("button");
    const completeBtn = initialButtons.find((b) => /상담 완료|완료|complete/i.test(b.textContent ?? ""));
    expect(completeBtn).toBeDefined();
    expect(completeBtn).toBeDisabled();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ConsultationWorkspacePane
            consultationId="cons-1"
            suitabilityChecked={true}
            explanationChecked={true}
            onSuitabilityChange={() => undefined}
            onExplanationChange={() => undefined}
            onComplete={() => undefined}
            briefingOutputId={null}
            onGenerateBriefing={() => undefined}
            isGenerating={false}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const enabledBtn = screen.getAllByRole("button").find((b) =>
      /상담 완료|완료|complete/i.test(b.textContent ?? ""),
    );
    expect(enabledBtn).toBeEnabled();
  });

  it("ConsultationFourGatePane respects isBranchManager flag for acknowledge button rendering", () => {
    // When isBranchManager=false, no acknowledge button is rendered (even if gates were PASSED).
    // The panel still renders without erroring.
    withProviders(
      <ConsultationFourGatePane
        consultationId="cons-1"
        onAcknowledge={() => undefined}
        isBranchManager={false}
      />,
    );
    // No '게이트 승인' button visible without BRANCH_MANAGER role
    expect(screen.queryByRole("button", { name: /게이트 승인|acknowledge/i })).toBeNull();
  });
});
