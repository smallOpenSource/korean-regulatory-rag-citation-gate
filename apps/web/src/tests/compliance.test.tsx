import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { allRecommendationGatesPass, consultationCanComplete } from "../lib/compliance";
import { SimulationPanel } from "../components/SimulationPanel";

describe("consultation completion gates", () => {
  it("requires suitability and explanation checks", () => {
    expect(consultationCanComplete(false, false)).toBe(false);
    expect(consultationCanComplete(true, false)).toBe(false);
    expect(consultationCanComplete(false, true)).toBe(false);
    expect(consultationCanComplete(true, true)).toBe(true);
  });
});

describe("recommendation/order simulation gates", () => {
  it("approves only when all four gates pass", () => {
    expect(
      allRecommendationGatesPass({
        suitabilityPassed: true,
        explanationChecked: true,
        simulatedCustomerConsented: true,
        employeeFinalApproved: false,
      }),
    ).toBe(false);
    expect(
      allRecommendationGatesPass({
        suitabilityPassed: true,
        explanationChecked: true,
        simulatedCustomerConsented: true,
        employeeFinalApproved: true,
      }),
    ).toBe(true);
  });

  it("renders the actual-order prohibition badge and gate-driven status", async () => {
    render(<SimulationPanel />);
    expect(screen.getByText("시뮬레이션 / 실제 주문 아님")).toBeInTheDocument();
    expect(screen.getByText("차단")).toBeInTheDocument();

    const user = userEvent.setup();
    for (const checkbox of screen.getAllByRole("checkbox")) {
      await user.click(checkbox);
    }
    expect(screen.getByText("승인")).toBeInTheDocument();
  });
});
